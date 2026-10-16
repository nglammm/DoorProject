import time
import RPi.GPIO as GPIO

# Relay pin definitions
RELAY_1 = 23
RELAY_2 = 24

def init_gpio():
    """Configures GPIO pins and ensures both relays are turned OFF."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RELAY_1, GPIO.OUT)
    GPIO.setup(RELAY_2, GPIO.OUT)
    # Active-LOW relays: HIGH = OFF
    GPIO.output(RELAY_1, GPIO.HIGH)
    GPIO.output(RELAY_2, GPIO.HIGH)

def stop_actuator():
    """Turns both relays OFF to safely halt motor movement."""
    GPIO.output(RELAY_1, GPIO.HIGH)
    GPIO.output(RELAY_2, GPIO.HIGH)

def retract(duration=None):
    """
    Retracts the linear actuator.
    :param duration: Time in seconds to run. If None, runs continuously until interrupted.
    """
    init_gpio()
    try:
        print("Retracting actuator...")
        # Relay 1 OFF (GND to Red), Relay 2 ON (+12V to Black)
        GPIO.output(RELAY_1, GPIO.HIGH)
        GPIO.output(RELAY_2, GPIO.LOW)

        if duration is not None:
            time.sleep(duration)
        else:
            print("Running continuously. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping command received.")
    finally:
        stop_actuator()
        GPIO.cleanup()
        print("Actuator stopped and GPIO cleaned up.")

if __name__ == "__main__":
    retract()