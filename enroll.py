import os
import re
import sys
import time
import cv2
import numpy as np
import sounddevice as sd
import face_recognition
from resemblyzer import VoiceEncoder, preprocess_wav

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
VOICES_DIR = os.path.join(BASE_DIR, "enrolled_voices")

CAMERA_INDEX = 0
SAMPLE_RATE = 16000
VOICE_DURATION = 5  # Seconds per voice sample
VOICE_SAMPLES = 3


def get_next_photo_number(name, authority):
    """Returns the next available photo number for '<name>_<authority>_<num>.png'."""
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR)
        return 1

    pattern = re.compile(rf"^{re.escape(name)}_(\d+)_(\d+)\.(png|jpg|jpeg)$", re.IGNORECASE)
    max_num = 0

    for filename in os.listdir(FACES_DIR):
        match = pattern.match(filename)
        if match:
            photo_num = int(match.group(2))
            if photo_num > max_num:
                max_num = photo_num

    return max_num + 1


def has_display():
    """Checks if a graphical display environment (X11/Wayland) is available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def enroll_face(name, authority):
    """Runs the webcam face enrollment flow."""
    gui_available = has_display()
    use_gui = False
    if gui_available:
        mode = input("Display detected. Use live video preview window? [Y/n]: ").strip().lower()
        use_gui = mode in ("", "y", "yes")
    else:
        print("[INFO] No display detected (running via SSH/headless). Using terminal prompt mode.")

    print(f"\n[INFO] Opening USB webcam (Index {CAMERA_INDEX})...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[ERROR] Could not open webcam! Ensure 'face-door.service' is stopped first:")
        print("        sudo systemctl stop face-door.service")
        return

    for _ in range(10):
        cap.read()

    next_num = get_next_photo_number(name, authority)
    saved_count = 0

    try:
        if use_gui:
            print("\n--- GUI Mode Instructions ---")
            print("  [SPACE] : Capture and save photo")
            print("  [Q]     : Finish face enrollment")
            print("-----------------------------\n")

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[WARN] Failed to read frame from camera.")
                    time.sleep(0.5)
                    continue

                display_frame = frame.copy()
                cv2.putText(
                    display_frame,
                    f"Enrolling: {name} (Lvl {authority}) | Saved: {saved_count}",
                    (10, 30), cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 255, 0), 1
                )
                cv2.putText(
                    display_frame,
                    "SPACE = Capture | Q = Quit",
                    (10, 460), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1
                )

                cv2.imshow("Enroll Face", display_frame)
                key = cv2.waitKey(1) & 0xFF

                if key == ord(" "):
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    boxes = face_recognition.face_locations(rgb_frame)

                    if len(boxes) == 0:
                        print("[REJECTED] No face detected in frame! Look clearly at the camera.")
                    elif len(boxes) > 1:
                        print(f"[REJECTED] Multiple faces ({len(boxes)}) detected! Only one person allowed.")
                    else:
                        filename = f"{name}_{authority}_{next_num}.png"
                        filepath = os.path.join(FACES_DIR, filename)
                        cv2.imwrite(filepath, frame)
                        print(f"[SUCCESS] Saved: {filepath}")
                        next_num += 1
                        saved_count += 1

                elif key == ord("q"):
                    break
        else:
            print("\n--- Headless / Terminal Mode Instructions ---")
            print("  Press [ENTER] to snap a photo, or type 'q' + [ENTER] to finish.")
            print("  Tip: Take 3-5 photos (front-facing, slight angles, with/without glasses).")
            print("---------------------------------------------\n")

            while True:
                cmd = input(f"[Ready for Photo #{next_num}] Position face and press ENTER (or 'q' to finish): ").strip().lower()
                if cmd == "q":
                    break

                for _ in range(5):
                    cap.grab()
                ret, frame = cap.read()

                if not ret:
                    print("[ERROR] Failed to capture frame from webcam.")
                    continue

                print("Verifying face in image...")
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                boxes = face_recognition.face_locations(rgb_frame)

                if len(boxes) == 0:
                    print("  -> [REJECTED] No face detected! Adjust lighting/position and try again.\n")
                elif len(boxes) > 1:
                    print(f"  -> [REJECTED] {len(boxes)} faces detected! Make sure only {name} is in view.\n")
                else:
                    filename = f"{name}_{authority}_{next_num}.png"
                    filepath = os.path.join(FACES_DIR, filename)
                    cv2.imwrite(filepath, frame)
                    print(f"  -> [SUCCESS] Valid face saved to: faces/{filename}\n")
                    next_num += 1
                    saved_count += 1

    except KeyboardInterrupt:
        print("\n[INFO] Face enrollment interrupted.")
    finally:
        cap.release()
        if use_gui:
            cv2.destroyAllWindows()
        print(f"[DONE] Enrolled {saved_count} new photo(s) for '{name}' (Authority {authority}).")


def enroll_voice(name, authority):
    """Records voice samples and saves '<name>_<authority>.npy' in enrolled_voices/."""
    os.makedirs(VOICES_DIR, exist_ok=True)

    # Remove older voice profiles for this user so authority updates cleanly
    for existing in os.listdir(VOICES_DIR):
        if existing.lower().startswith(f"{name.lower()}_") and existing.endswith(".npy"):
            os.remove(os.path.join(VOICES_DIR, existing))

    print("\n[INFO] Loading Resemblyzer Voice Encoder model...")
    encoder = VoiceEncoder()

    embeddings = []
    sample_idx = 1

    print("\n--- Voice Enrollment Instructions ---")
    print(f"  You will record {VOICE_SAMPLES} voice samples ({VOICE_DURATION} seconds each).")
    print("  Speak naturally and continuously (e.g., say passphrases or count numbers).")
    print("-------------------------------------")

    try:
        while sample_idx <= VOICE_SAMPLES:
            input(f"\nPress [ENTER] when ready to record sample {sample_idx}/{VOICE_SAMPLES}...")
            print(f"[{sample_idx}/{VOICE_SAMPLES}] Prepare to speak...")
            sd.sleep(500)
            print(f">>> SPEAK NOW for {VOICE_DURATION} seconds <<<")

            recording = sd.rec(
                int(VOICE_DURATION * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32"
            )
            sd.wait()
            print("Done recording sample.")

            audio_data = np.squeeze(recording)
            wav = preprocess_wav(audio_data, source_sr=SAMPLE_RATE)

            if len(wav) < SAMPLE_RATE * 1.2:
                print("[REJECTED] Audio too quiet or short! Please speak clearly and try this sample again.")
                continue

            embed = encoder.embed_utterance(wav)
            embeddings.append(embed)
            print(f"[SUCCESS] Sample {sample_idx} accepted.")
            sample_idx += 1

        # Average and normalize speaker embedding
        mean_embedding = np.mean(embeddings, axis=0)
        mean_embedding = mean_embedding / np.linalg.norm(mean_embedding)

        filename = f"{name}_{authority}.npy"
        filepath = os.path.join(VOICES_DIR, filename)
        np.save(filepath, mean_embedding)
        print(f"\n[DONE] Voice profile saved to: enrolled_voices/{filename}")

    except KeyboardInterrupt:
        print("\n[INFO] Voice enrollment interrupted.")


def main():
    print("=== RPi5 Biometric Enrollment Tool (Face & Voice) ===")

    # 1. Prompt for Name
    while True:
        name = input("Enter person's name (e.g., alice): ").strip()
        name = name.replace(" ", "-").replace("_", "-")
        if name:
            break
        print("[ERROR] Name cannot be empty.")

    # 2. Prompt for Authority Level
    while True:
        auth_str = input("Enter authority level (integer, >= 2 opens door): ").strip()
        try:
            authority = int(auth_str)
            break
        except ValueError:
            print("[ERROR] Authority level must be a valid integer (e.g., 1, 2, 3).")

    # 3. Choose Enrollment Mode
    print("\nSelect enrollment mode:")
    print("  [1] Camera (Face only)")
    print("  [2] Microphone (Voice only)")
    print("  [3] Both Face and Voice")
    while True:
        choice = input("Enter choice (1/2/3) [default: 3]: ").strip()
        if choice in ("", "3"):
            mode = "both"
            break
        elif choice == "1":
            mode = "face"
            break
        elif choice == "2":
            mode = "voice"
            break
        print("[ERROR] Invalid choice. Please enter 1, 2, or 3.")

    if mode in ("face", "both"):
        enroll_face(name, authority)

    if mode in ("voice", "both"):
        enroll_voice(name, authority)

    print("\n[REMINDER] Restart your systemd service to load the new profiles:")
    print("           sudo systemctl restart face-door.service")


if __name__ == "__main__":
    main()