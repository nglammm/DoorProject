# actuator_control.py
import time
import argparse
import threading
import RPi.GPIO as GPIO

RELAY_1 = 24
RELAY_2 = 23

def init_gpio():
    """Initializes pins once with relays OFF (Active-LOW: HIGH = OFF)."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RELAY_1, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.setup(RELAY_2, GPIO.OUT, initial=GPIO.HIGH)

def stop_actuator():
    """Immediately turns both relays OFF to cut motor power."""
    try:
        GPIO.output(RELAY_1, GPIO.HIGH)
        GPIO.output(RELAY_2, GPIO.HIGH)
    except Exception:
        pass

def cleanup_gpio():
    """Safely halts motor and cleans up GPIO state."""
    stop_actuator()
    try:
        GPIO.cleanup()
    except Exception:
        pass

def extend(duration=None, stop_event=None):
    """
    Extends actuator. Replaces time.sleep with stop_event checks for instant abort.
    """
    init_gpio()
    try:
        if stop_event and stop_event.is_set():
            return
        # Relay 1 ON (LOW), Relay 2 OFF (HIGH)
        GPIO.output(RELAY_1, GPIO.LOW)
        GPIO.output(RELAY_2, GPIO.HIGH)

        if duration is not None:
            if stop_event:
                stop_event.wait(timeout=duration)
            else:
                time.sleep(duration)
        else:
            if stop_event:
                while not stop_event.is_set():
                    time.sleep(0.1)
            else:
                while True:
                    time.sleep(0.1)
    finally:
        stop_actuator()

def retract(duration=None, stop_event=None):
    """
    Retracts actuator. Replaces time.sleep with stop_event checks for instant abort.
    """
    init_gpio()
    try:
        if stop_event and stop_event.is_set():
            return
        # Relay 1 OFF (HIGH), Relay 2 ON (LOW)
        GPIO.output(RELAY_1, GPIO.HIGH)
        GPIO.output(RELAY_2, GPIO.LOW)

        if duration is not None:
            if stop_event:
                stop_event.wait(timeout=duration)
            else:
                time.sleep(duration)
        else:
            if stop_event:
                while not stop_event.is_set():
                    time.sleep(0.1)
            else:
                while True:
                    time.sleep(0.1)
    finally:
        stop_actuator()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Manual linear actuator controller for Raspberry Pi."
    )
    
    # Mutually exclusive group: user must choose extend OR retract
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--extend", "-extend", "-e",
        action="store_true",
        help="Extend the actuator"
    )
    action_group.add_argument(
        "--retract", "-retract", "-r",
        action="store_true",
        help="Retract the actuator"
    )

    # Optional duration parameter
    parser.add_argument(
        "--duration", "-duration", "-d",
        type=float,
        default=None,
        help="Run duration in seconds as a float (e.g. 5.5). If omitted, runs indefinitely until Ctrl+C."
    )

    args = parser.parse_args()
    cli_stop_event = threading.Event()

    action_label = "Extending" if args.extend else "Retracting"
    duration_label = f"for {args.duration:.2f}s" if args.duration is not None else "indefinitely (Press Ctrl+C to halt)"
    print(f"[ACTUATOR] {action_label} {duration_label}...", flush=True)

    try:
        if args.extend:
            extend(duration=args.duration, stop_event=cli_stop_event)
        elif args.retract:
            retract(duration=args.duration, stop_event=cli_stop_event)
    except KeyboardInterrupt:
        print("\n[STOP] Received Ctrl+C. Halting actuator immediately...", flush=True)
        cli_stop_event.set()
    finally:
        cleanup_gpio()
        print("[CLEANUP] Actuator stopped and GPIO released.", flush=True)