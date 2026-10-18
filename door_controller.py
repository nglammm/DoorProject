import os
import time
import json
import queue
import signal
import sys
import threading
import asyncio
import cv2
import face_recognition
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
from resemblyzer import VoiceEncoder, preprocess_wav

from voice import say
from actuator_control import extend, retract, stop_actuator, cleanup_gpio

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
VOICES_DIR = os.path.join(BASE_DIR, "enrolled_voices")
VOSK_MODEL_PATH = os.path.join(BASE_DIR, "model")

CAMERA_INDEX = 0
ACTUATOR_DURATION = 30
OPEN_DELAY = 5
MIN_AUTHORITY = 2
PROCESS_EVERY_N_FRAMES = 4
DISPLAY_VIDEO = False
TTS_COOLDOWN = 6.0

# Voice Configuration
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000  # 0.25s audio chunks
VOICE_SIMILARITY_THRESHOLD = 0.7  # Adjust between 0.72 (lenient) and 0.80 (strict)
MIN_SPEECH_SECONDS = 0.2  # Minimum active speech length to verify speaker

# Voice Command Phrases (supports common Vosk misrecognitions too)
OPEN_COMMANDS = ("open door", "open the door", "open")
CLOSE_COMMANDS = ("close door", "close the door", "closed door", "close")

# Suppress Vosk log spam
SetLogLevel(-1)

# Shutdown & Door Preemption Coordinators
stop_event = threading.Event()
door_abort_event = threading.Event()

# Locks and tracking
door_lock = threading.Lock()
is_door_busy = False
current_door_thread = None

tts_lock = threading.Lock()
is_speaking = False
last_speech_time = 0.0


class CompositeEvent:
    """
    Combines the global stop_event and the per-command door_abort_event
    so retract() and extend() wake up and stop immediately if EITHER is triggered.
    """
    def __init__(self, *events):
        self.events = events

    def is_set(self):
        return any(e.is_set() for e in self.events)

    def wait(self, timeout=None):
        start = time.time()
        while not self.is_set():
            if timeout is not None and (time.time() - start) >= timeout:
                return False
            time.sleep(0.05)
        return True


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
        if is_speaking and not force:
            return
        if not force and (now - last_speech_time) < TTS_COOLDOWN:
            return
        is_speaking = True

    thread = threading.Thread(target=_play_tts_worker, args=(text,), daemon=True)
    thread.start()


# --- Profile Loaders (Faces & Voices) ---

def load_known_faces(directory):
    known_encodings = []
    known_names = []
    known_authorities = []

    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[WARNING] Created '{directory}/' folder. Run enroll.py to add faces.", flush=True)
        return known_encodings, known_names, known_authorities

    print(f"[INFO] Loading faces from '{directory}/'...", flush=True)
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
                print(f"  -> Loaded Face: {name} | Authority: {authority} | Photo #{photo_num}", flush=True)

    return known_encodings, known_names, known_authorities


def load_known_voices(directory):
    voice_profiles = []
    if not os.path.exists(directory):
        os.makedirs(directory)
        print(f"[WARNING] Created '{directory}/' folder. Run enroll.py to add voices.", flush=True)
        return voice_profiles

    print(f"[INFO] Loading voices from '{directory}/'...", flush=True)
    for filename in sorted(os.listdir(directory)):
        if filename.lower().endswith(".npy"):
            base_name = os.path.splitext(filename)[0]
            parts = base_name.rsplit("_", 1)

            if len(parts) == 2 and parts[1].isdigit():
                name = parts[0]
                authority = int(parts[1])
            else:
                name = base_name
                authority = MIN_AUTHORITY

            filepath = os.path.join(directory, filename)
            embedding = np.load(filepath)
            voice_profiles.append({
                "name": name,
                "authority": authority,
                "embedding": embedding
            })
            print(f"  -> Loaded Voice: {name} | Authority: {authority}", flush=True)

    return voice_profiles


# --- Door Control (Supports Normal Cycle + Force Open / Force Close) ---

def operate_door(person_name, authority, source="Biometric", action="cycle"):
    """
    action can be:
      - 'cycle'       : Normal open -> wait -> close
      - 'force_open'  : Immediately open door and stay open
      - 'force_close' : Immediately close door and stay closed
    """
    global is_door_busy
    active_event = CompositeEvent(stop_event, door_abort_event)

    try:
        if action == "force_open":
            print(f"\n[FORCE OPEN via {source}] {person_name} (Authority: {authority}) ordered OPEN DOOR!", flush=True)
            speak_vn_async(f"Đang mở cửa theo lệnh của {person_name}", force=True)

            print(f"[DOOR] Force-opening door for {ACTUATOR_DURATION}s...", flush=True)
            retract(duration=ACTUATOR_DURATION, stop_event=active_event)

            if not active_event.is_set():
                print("[DOOR] Force-open complete. Door remains open.\n", flush=True)

        elif action == "force_close":
            print(f"\n[FORCE CLOSE via {source}] {person_name} (Authority: {authority}) ordered CLOSE DOOR!", flush=True)
            speak_vn_async(f"Đang đóng cửa theo lệnh của {person_name}", force=True)

            print(f"[DOOR] Force-closing door for {ACTUATOR_DURATION}s...", flush=True)
            extend(duration=ACTUATOR_DURATION, stop_event=active_event)

            if not active_event.is_set():
                print("[DOOR] Force-close complete. Door remains closed.\n", flush=True)

        else:
            # Standard automatic cycle
            print(f"\n[ACCESS GRANTED via {source}] Welcome {person_name} (Authority: {authority}).", flush=True)
            speak_vn_async(f"Chào mừng {person_name} trở về", force=True)

            print(f"[DOOR] Opening door for {ACTUATOR_DURATION}s...", flush=True)
            retract(duration=ACTUATOR_DURATION, stop_event=active_event)

            if active_event.is_set():
                return

            print(f"[DOOR] Door open. Waiting {OPEN_DELAY}s...", flush=True)
            active_event.wait(timeout=OPEN_DELAY)

            if active_event.is_set():
                return

            print(f"[DOOR] Closing door for {ACTUATOR_DURATION}s...", flush=True)
            extend(duration=ACTUATOR_DURATION, stop_event=active_event)

            if not active_event.is_set():
                print("[DOOR] Door cycle complete.\n", flush=True)

    except Exception as e:
        print(f"[ERROR] Door operation error: {e}", flush=True)
    finally:
        stop_actuator()
        with door_lock:
            is_door_busy = False


def trigger_door_async(person_name, authority, source="Biometric", action="cycle", force=False):
    """
    Starts a door operation. If force=True and the door is currently moving/waiting,
    it immediately aborts the running door thread and executes the new action.
    """
    global is_door_busy, current_door_thread

    if stop_event.is_set():
        return

    if force:
        # Check if an existing door thread is active and preempt it
        thread_to_wait = None
        with door_lock:
            if is_door_busy and current_door_thread is not None and current_door_thread.is_alive():
                print(f"[OVERRIDE] Aborting active door task for forced command ({action})...", flush=True)
                door_abort_event.set()
                stop_actuator()
                thread_to_wait = current_door_thread

        if thread_to_wait is not None:
            thread_to_wait.join(timeout=2.0)

        with door_lock:
            door_abort_event.clear()
            is_door_busy = True
            current_door_thread = threading.Thread(
                target=operate_door,
                args=(person_name, authority, source, action),
                daemon=True
            )
            current_door_thread.start()
    else:
        with door_lock:
            if is_door_busy:
                return
            door_abort_event.clear()
            is_door_busy = True
            current_door_thread = threading.Thread(
                target=operate_door,
                args=(person_name, authority, source, action),
                daemon=True
            )
            current_door_thread.start()


# --- Continuous Background Voice Recognition Thread ---

def identify_speaker(encoder, audio_int16, voice_profiles):
    audio_float32 = audio_int16.astype(np.float32) / 32768.0
    wav = preprocess_wav(audio_float32, source_sr=SAMPLE_RATE)

    if len(wav) < SAMPLE_RATE * MIN_SPEECH_SECONDS:
        return "Too Short", 0, 0.0

    utterance_embed = encoder.embed_utterance(wav)

    best_name = "Unknown"
    best_auth = 0
    best_score = -1.0

    for profile in voice_profiles:
        score = float(np.dot(utterance_embed, profile["embedding"]))
        if score > best_score:
            best_score = score
            best_name = profile["name"]
            best_auth = profile["authority"]

    if best_score >= VOICE_SIMILARITY_THRESHOLD:
        return best_name, best_auth, best_score
    return "Unknown", 0, best_score


def parse_voice_command(text):
    """Checks if spoken text contains a forceful open or close command."""
    cleaned = text.lower().strip()
    if any(cmd in cleaned for cmd in OPEN_COMMANDS):
        return "force_open"
    if any(cmd in cleaned for cmd in CLOSE_COMMANDS):
        return "force_close"
    return None


def voice_listener_worker(voice_profiles):
    """Continuously listens to the microphone in a background thread."""
    if not voice_profiles:
        print("[VOICE] No voice profiles loaded. Voice listener disabled.", flush=True)
        return

    if not os.path.exists(VOSK_MODEL_PATH):
        print(f"[VOICE ERROR] Vosk model not found at '{VOSK_MODEL_PATH}'. Voice listener disabled.", flush=True)
        return

    print("[VOICE] Initializing Resemblyzer and Vosk models...", flush=True)
    try:
        encoder = VoiceEncoder()
        vosk_model = Model(VOSK_MODEL_PATH)
        recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE)
    except Exception as e:
        print(f"[VOICE ERROR] Failed to load voice models: {e}", flush=True)
        return

    audio_queue = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"[AUDIO WARN] {status}", file=sys.stderr, flush=True)
        audio_queue.put(bytes(indata))

    current_phrase_pcm = bytearray()
    max_silence_bytes = SAMPLE_RATE * 2 * 3  # 3 seconds of 16-bit mono audio

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):
            print("[VOICE] Continuous microphone listener active. Say 'open door' or 'close door'.", flush=True)

            while not stop_event.is_set():
                try:
                    data = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                # Ignore microphone input while speaker TTS is playing (prevents self-triggering)
                if is_speaking or (time.time() - last_speech_time) < 0.5:
                    current_phrase_pcm = bytearray()
                    recognizer.Reset()
                    continue

                current_phrase_pcm.extend(data)

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()

                    if text:
                        # Convert bytearray to immutable bytes() first to prevent BufferError
                        pcm_bytes = bytes(current_phrase_pcm)
                        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16)

                        speaker, authority, confidence = identify_speaker(
                            encoder, audio_np, voice_profiles
                        )
                        command_action = parse_voice_command(text)

                        print(
                            f"[VOICE] Heard ({speaker} | Auth {authority} | Sim {confidence:.2f}): '{text}'",
                            flush=True
                        )

                        if speaker == "Too Short":
                            pass
                        elif speaker != "Unknown" and authority >= MIN_AUTHORITY:
                            if command_action == "force_open":
                                trigger_door_async(
                                    speaker, authority, source="Voice Command", action="force_open", force=True
                                )
                            elif command_action == "force_close":
                                trigger_door_async(
                                    speaker, authority, source="Voice Command", action="force_close", force=True
                                )
                            else:
                                # Spoken phrase without a specific command triggers standard door cycle
                                trigger_door_async(
                                    speaker, authority, source="Voice", action="cycle", force=False
                                )
                        else:
                            if not is_door_busy:
                                speak_vn_async("cút ra ngoài")

                    # Reset buffer cleanly for next phrase
                    current_phrase_pcm = bytearray()
                else:
                    partial = json.loads(recognizer.PartialResult()).get("partial", "")
                    if not partial and len(current_phrase_pcm) > max_silence_bytes:
                        current_phrase_pcm = bytearray(current_phrase_pcm[-(SAMPLE_RATE * 2):])

    except Exception as e:
        if not stop_event.is_set():
            print(f"[VOICE ERROR] Microphone stream crashed: {e}", flush=True)


# --- Shutdown & Main Loop ---

def shutdown(signum=None, frame=None):
    """Coordinated shutdown routine."""
    print("\n[INFO] Shutdown signal received. Halting hardware...", flush=True)
    stop_event.set()
    door_abort_event.set()
    stop_actuator()
    cleanup_gpio()
    if signum is not None:
        sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    known_encodings, known_names, known_authorities = load_known_faces(FACES_DIR)
    voice_profiles = load_known_voices(VOICES_DIR)

    if not known_encodings and not voice_profiles:
        print("[ERROR] Neither faces nor voices are enrolled! Run enroll.py first. Exiting.", flush=True)
        return

    # Start continuous voice recognition in background thread
    voice_thread = threading.Thread(
        target=voice_listener_worker,
        args=(voice_profiles,),
        daemon=True
    )
    voice_thread.start()

    # Open camera if faces are enrolled
    video_capture = None
    if known_encodings:
        print("[INFO] Opening USB webcam stream...", flush=True)
        video_capture = cv2.VideoCapture(CAMERA_INDEX)
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not video_capture.isOpened():
            print("[WARN] Could not open USB webcam. Running in Voice-Only mode.", flush=True)
            video_capture = None

    print("[INFO] System active. Listening & watching continuously. Press Ctrl+C to exit.", flush=True)
    frame_count = 0

    try:
        while not stop_event.is_set():
            if video_capture is None:
                stop_event.wait(timeout=0.5)
                continue

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
                        trigger_door_async(name, authority, source="Face", action="cycle", force=False)
                    else:
                        if not is_door_busy:
                            speak_vn_async("cút ra ngoài")

            if DISPLAY_VIDEO:
                cv2.imshow("RPi5 Face & Voice Access Control", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    finally:
        shutdown()
        if video_capture is not None:
            video_capture.release()
        if DISPLAY_VIDEO:
            cv2.destroyAllWindows()
        print("[INFO] Clean exit complete.", flush=True)


if __name__ == "__main__":
    main()