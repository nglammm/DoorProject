import os
import re
import time
import cv2
import face_recognition

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "faces")
CAMERA_INDEX = 0


def get_next_photo_number(name, authority):
    """
    Scans the faces/ directory for existing photos of this person and returns
    the next available photo number so existing files aren't overwritten.
    """
    if not os.path.exists(FACES_DIR):
        os.makedirs(FACES_DIR)
        return 1

    # Match files like '<name>_<authority>_<num>.png' or '<name>_<any_auth>_<num>.png'
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


def main():
    print("=== RPi5 Face Enrollment Tool ===")
    
    # 1. Prompt for Name
    while True:
        name = input("Enter person's name (e.g., alice): ").strip()
        # Replace spaces with hyphens so the '_' delimiter remains clean
        name = name.replace(" ", "-")
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

    # 3. Choose Mode (Auto-detect headless SSH vs desktop GUI)
    gui_available = has_display()
    use_gui = False
    if gui_available:
        mode = input("Display detected. Use live video preview window? [Y/n]: ").strip().lower()
        use_gui = mode in ("", "y", "yes")
    else:
        print("[INFO] No display detected (running via SSH/headless). Using terminal prompt mode.")

    # 4. Open Camera
    print(f"\n[INFO] Opening USB webcam (Index {CAMERA_INDEX})...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[ERROR] Could not open webcam! Ensure 'face-door.service' is stopped first:")
        print("        sudo systemctl stop face-door.service")
        return

    # Warm up camera sensor for auto-exposure
    for _ in range(10):
        cap.read()

    next_num = get_next_photo_number(name, authority)
    saved_count = 0

    try:
        if use_gui:
            print("\n--- GUI Mode Instructions ---")
            print("  [SPACE] : Capture and save photo")
            print("  [Q]     : Quit enrollment")
            print("-----------------------------\n")

            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[WARN] Failed to read frame from camera.")
                    time.sleep(0.5)
                    continue

                display_frame = frame.copy()

                # Draw guide text on preview
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
                        print("[REJECTED] No face detected in frame! Look clearly at the camera and try again.")
                    elif len(boxes) > 1:
                        print(f"[REJECTED] Multiple faces ({len(boxes)}) detected! Only one person should be in frame.")
                    else:
                        filename = f"{name}_{authority}_{next_num}.png"
                        filepath = os.path.join(FACES_DIR, filename)
                        # Save the clean, un-annotated frame
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
                cmd = input(f"[Ready for Photo #{next_num}] Position face in front of camera and press ENTER (or 'q' to quit): ").strip().lower()
                if cmd == "q":
                    break

                # Flush old buffered frames from OpenCV so we get the exact current moment
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
                    print(f"  -> [SUCCESS] Valid face detected and saved to: faces/{filename}\n")
                    next_num += 1
                    saved_count += 1

    except KeyboardInterrupt:
        print("\n[INFO] Enrollment interrupted by user.")
    finally:
        cap.release()
        if use_gui:
            cv2.destroyAllWindows()
        print(f"\n[DONE] Enrolled {saved_count} new photo(s) for '{name}' (Authority {authority}).")
        print("[REMINDER] Restart your systemd service to load the new faces:")
        print("           sudo systemctl restart face-door.service")


if __name__ == "__main__":
    main()