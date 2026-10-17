import os
import time
import threading
import hashlib
import cv2
import face_recognition
import numpy as np
from gtts import gTTS
import pygame

from extend_actuator import extend
from retract_actuator import retract

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
TTS_CACHE_DIR = os.path.join(BASE_DIR, "tts_cache")
CAMERA_INDEX = 0           # Default USB webcam
ACTUATOR_DURATION = 30     # Seconds to extend/retract
OPEN_DELAY = 5             # Seconds to wait before closing
MIN_AUTHORITY = 2          # Minimum authority level required to open the door
PROCESS_EVERY_N_FRAMES = 4 # Process 1 out of N frames to keep RPi 5 CPU cool
DISPLAY_VIDEO = False      # MUST be False when running as a background systemd service

# Debounce interval in seconds (prevents repeating speech on consecutive frames)
TTS_COOLDOWN = 6.0

# Initialize Pygame Mixer for non-blocking playback
pygame.mixer.init()
if not os.path.exists(TTS_CACHE_DIR):
    os.makedirs(TTS_CACHE_DIR)

# Locks and state flags
door_lock = threading.Lock()
is_door_busy = False

tts_lock = threading.Lock()
is_speaking = False
last_speech_time = 0.0


# --- Vietnamese Text-to-Speech Functions ---

def _play_tts_worker(text):
    """
    Worker function to fetch/cache MP3 and play via pygame mixer.
    """
    global is_speaking, last_speech_time
    try:
        # Cache file based on MD5 of text to avoid re-downloading on every scan
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cache_path = os.path.join(TTS_CACHE_DIR, f"{text_hash}.mp3")

        if not os.path.exists(cache_path):
            tts = gTTS(text=text, lang='vi')
            tts.save(cache_path)

        pygame.mixer.music.load(cache_path)
        pygame.mixer.music.play()

        # Wait until playback finishes before releasing the lock
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

    except Exception as e:
        print(f"[TTS ERROR] Failed to speak '{text}': {e}", flush=True)
    finally:
        with tts_lock:
            last_speech_time = time.time()
            is_speaking = False


def speak_vn_async(text, force=False):
    """
    Non-blocking TTS trigger with cooldown to avoid spamming the audio device.
    """
    global is_speaking, last_speech_time
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
                print(f"[SKIP] '{filename}' does not match '<name>_<authority_level>_<photo_number>'.")
                continue

            try:
                authority = int(auth_str)
            except ValueError:
                print(f"[SKIP] Invalid authority level '{auth_str}' in '{filename}'. Must be an integer.")
                continue

            filepath = os.path.join(directory, filename)
            image = face_recognition.load_image_file(filepath)
            encodings = face_recognition.face_encodings(image)

            if len(encodings) > 0:
                known_encodings.append(encodings[0])
                known_names.append(name)
                known_authorities.append(authority)
                print(f"  -> Loaded: {name} | Authority: {authority} | Photo #{photo_num}")
            else:
                print(f"[WARN] No face detected in '{filename}'. Skipping.")

    return known_encodings, known_names, known_authorities


def operate_door(person_name, authority):
    """
    Executes door cycle in background thread and triggers welcome greeting.
    """
    global is_door_busy
    try:
        print(f"\n[ACCESS GRANTED] Welcome {person_name} (Authority: {authority}).", flush=True)

        # Trigger welcome voice in Vietnamese
        speak_vn_async(f"Chào mừng {person_name} trở về", force=True)

        print(f"[DOOR] Opening door for {ACTUATOR_DURATION} seconds...", flush=True)
        retract(duration=ACTUATOR_DURATION)

        print(f"[DOOR] Door fully open. Waiting {OPEN_DELAY} seconds...", flush=True)
        time.sleep(OPEN_DELAY)

        print(f"[DOOR] Closing door for {ACTUATOR_DURATION} seconds...", flush=True)
        extend(duration=ACTUATOR_DURATION)

        print("[DOOR] Door cycle complete. Ready for next scan.\n", flush=True)
    except Exception as e:
        print(f"[ERROR] Door operation encountered an error: {e}", flush=True)
    finally:
        with door_lock:
            is_door_busy = False


def trigger_door_async(person_name, authority):
    global is_door_busy
    with door_lock:
        if is_door_busy:
            return
        is_door_busy = True

    door_thread = threading.Thread(
        target=operate_door, 
        args=(person_name, authority), 
        daemon=True
    )
    door_thread.start()


def main():
    known_encodings, known_names, known_authorities = load_known_faces(FACES_DIR)
    if not known_encodings:
        print("[ERROR] No valid faces loaded. Exiting.", flush=True)
        return

    print("[INFO] Opening USB webcam stream...", flush=True)
    video_capture = cv2.VideoCapture(CAMERA_INDEX)
    video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not video_capture.isOpened():
        print("[ERROR] Could not open USB webcam. Check connection and CAMERA_INDEX.", flush=True)
        return

    print("[INFO] System running and monitoring webcam feed...", flush=True)

    frame_count = 0
    face_locations = []
    face_labels = []
    face_colors = []

    try:
        while True:
            ret, frame = video_capture.read()
            if not ret:
                print("[WARN] Failed to grab frame from webcam. Retrying...", flush=True)
                time.sleep(0.5)
                continue

            frame_count += 1

            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                face_labels = []
                face_colors = []

                for face_encoding in face_encodings:
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
                    name = "Unknown"
                    authority = 0
                    color = (0, 0, 255)

                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            name = known_names[best_match_index]
                            authority = known_authorities[best_match_index]

                    # Decision logic for authority & voice
                    if name != "Unknown" and authority >= MIN_AUTHORITY:
                        color = (0, 255, 0)
                        trigger_door_async(name, authority)
                    else:
                        # Triggers for either Unknown faces or known faces with authority < MIN_AUTHORITY
                        if not is_door_busy:
                            if name == "Unknown":
                                print("[ACCESS DENIED] Unknown person detected.", flush=True)
                            else:
                                print(f"[ACCESS DENIED] {name} (Authority {authority} < {MIN_AUTHORITY})", flush=True)
                            
                            speak_vn_async("cút ra ngoài")

                    label = f"{name} (Lvl {authority})" if name != "Unknown" else "Unknown"
                    face_labels.append(label)
                    face_colors.append(color)

            if DISPLAY_VIDEO:
                for (top, right, bottom, left), label, color in zip(face_locations, face_labels, face_colors):
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4

                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
                    cv2.putText(frame, label, (left + 6, bottom - 8), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)

                if is_door_busy:
                    cv2.putText(frame, "DOOR OPERATING...", (15, 35), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 255), 2)

                cv2.imshow("RPi5 Face Access Control", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down face recognition...", flush=True)
    finally:
        video_capture.release()
        if DISPLAY_VIDEO:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()