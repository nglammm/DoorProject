import os
import time
import signal
import sys
import threading
import asyncio
import cv2
import face_recognition
import numpy as np

from voice import say
from actuator_control import extend, retract, stop_actuator, cleanup_gpio

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
CAMERA_INDEX = 0
ACTUATOR_DURATION = 30
OPEN_DELAY = 5
MIN_AUTHORITY = 2
PROCESS_EVERY_N_FRAMES = 4
DISPLAY_VIDEO = False
TTS_COOLDOWN = 6.0

# Shutdown coordinator
stop_event = threading.Event()

# Locks and tracking
door_lock = threading.Lock()
is_door_busy = False
current_door_thread = None

tts_lock = threading.Lock()
is_speaking = False
last_speech_time = 0.0


# --- Vietnamese Text-to-Speech Functions ---

def _play_tts_worker(text):
    global is_speaking, last_speech_time
    try:
        if stop_event.is_set():
            return
        asyncio.run(say(text))
    except Exception as e:
        print(f"[TTS ERROR] Failed to speak '{text}': {e}", flush=True)
    finally:
        with tts_lock:
            last_speech_time = time.time()
            is_speaking = False


def speak_vn_async(text, force=False):
    global is_speaking, last_speech_time
    if stop_event.is_set():
        return

    with tts_lock:
        now = time.time()
        if is_speaking:
            return
        if not force and (now - last_speech_time) < TTS_COOLDOWN:
            return
        is_speaking = True

    thread = threading.Thread(target=_play_tts_worker, args=(text,), daemon=True)
    thread.start()


# --- Face Recognition & Door Control ---

def load_known_faces(directory):
    known_encodings = []
    known_names = []
    known_authorities = []

    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[WARNING] Created '{directory}/' folder. Add '<name>_<authority>_<photo_num>.png' files.")
        return known_encodings, known_names, known_authorities

    print(f"[INFO] Loading faces from '{directory}/'...")
    for filename in sorted(os.listdir(directory)):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            base_name = os.path.splitext(filename)[0]
            parts = base_name.rsplit("_", 2)
            
            if len(parts) == 3:
                name, auth_str, photo_num = parts
            elif len(parts) == 2:
                name, auth_str = parts
                photo_num = "1"
            else:
                continue

            try:
                authority = int(auth_str)
            except ValueError:
                continue

            filepath = os.path.join(directory, filename)
            image = face_recognition.load_image_file(filepath)
            encodings = face_recognition.face_encodings(image)

            if len(encodings) > 0:
                known_encodings.append(encodings[0])
                known_names.append(name)
                known_authorities.append(authority)
                print(f"  -> Loaded: {name} | Authority: {authority} | Photo #{photo_num}")

    return known_encodings, known_names, known_authorities


def operate_door(person_name, authority):
    """
    Runs the door cycle with responsive stop_event checks at every stage.
    """
    global is_door_busy
    try:
        print(f"\n[ACCESS GRANTED] Welcome {person_name} (Authority: {authority}).", flush=True)
        speak_vn_async(f"Chào mừng {person_name} trở về", force=True)

        print(f"[DOOR] Opening door for {ACTUATOR_DURATION}s...", flush=True)
        retract(duration=ACTUATOR_DURATION, stop_event=stop_event)

        if stop_event.is_set():
            return

        print(f"[DOOR] Door open. Waiting {OPEN_DELAY}s...", flush=True)
        stop_event.wait(timeout=OPEN_DELAY)

        if stop_event.is_set():
            return

        print(f"[DOOR] Closing door for {ACTUATOR_DURATION}s...", flush=True)
        extend(duration=ACTUATOR_DURATION, stop_event=stop_event)

        if not stop_event.is_set():
            print("[DOOR] Door cycle complete.\n", flush=True)
    except Exception as e:
        print(f"[ERROR] Door operation error: {e}", flush=True)
    finally:
        stop_actuator()
        with door_lock:
            is_door_busy = False


def trigger_door_async(person_name, authority):
    global is_door_busy, current_door_thread
    with door_lock:
        if is_door_busy or stop_event.is_set():
            return
        is_door_busy = True

    current_door_thread = threading.Thread(
        target=operate_door, 
        args=(person_name, authority), 
        daemon=True
    )
    current_door_thread.start()


def shutdown(signum=None, frame=None):
    """Coordinated shutdown routine."""
    print("\n[INFO] Shutdown signal received. Halting hardware...", flush=True)
    stop_event.set()
    stop_actuator()
    cleanup_gpio()
    if signum is not None:
        sys.exit(0)


def main():
    # Trap SIGINT (Ctrl+C) and SIGTERM (systemctl stop / kill)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    known_encodings, known_names, known_authorities = load_faces = load_known_faces(FACES_DIR)
    if not known_encodings:
        print("[ERROR] No valid faces loaded. Exiting.", flush=True)
        return

    print("[INFO] Opening USB webcam stream...", flush=True)
    video_capture = cv2.VideoCapture(CAMERA_INDEX)
    video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not video_capture.isOpened():
        print("[ERROR] Could not open USB webcam.", flush=True)
        return

    print("[INFO] System active. Press Ctrl+C to safely exit.", flush=True)
    frame_count = 0

    try:
        while not stop_event.is_set():
            ret, frame = video_capture.read()
            if not ret:
                time.sleep(0.1)
                continue

            frame_count += 1
            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                for face_encoding in face_encodings:
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
                    name = "Unknown"
                    authority = 0

                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            name = known_names[best_match_index]
                            authority = known_authorities[best_match_index]

                    if name != "Unknown" and authority >= MIN_AUTHORITY:
                        trigger_door_async(name, authority)
                    else:
                        if not is_door_busy:
                            speak_vn_async("cút ra ngoài")

            if DISPLAY_VIDEO:
                cv2.imshow("RPi5 Face Access Control", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    finally:
        shutdown()
        video_capture.release()
        if DISPLAY_VIDEO:
            cv2.destroyAllWindows()
        print("[INFO] Clean exit complete.", flush=True)


if __name__ == "__main__":
    main()