# actuator_control.py
import time
import RPi.GPIO as GPIO

RELAY_1 = 23
RELAY_2 = 24

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
                # Returns True early if stop_event is triggered
                stop_event.wait(timeout=duration)
            else:
                time.sleep(duration)
        else:
            while stop_event and not stop_event.is_set():
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
            while stop_event and not stop_event.is_set():
                time.sleep(0.1)
    finally:
        stop_actuator()