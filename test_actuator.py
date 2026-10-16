import time
import RPi.GPIO as GPIO

# Define relay pins based on your setup
RELAY_1 = 23
RELAY_2 = 24

# Setup GPIO mode
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_1, GPIO.OUT)
GPIO.setup(RELAY_2, GPIO.OUT)

# Ensure both relays start OFF (HIGH is usually OFF for optoisolated relay modules)
# Note: If your relay triggers on HIGH instead of LOW, swap HIGH and LOW below.
GPIO.output(RELAY_1, GPIO.HIGH)
GPIO.output(RELAY_2, GPIO.HIGH)

try:
  print("Starting Linear Actuator Test Cycle...")

  # 1. Extend the Actuator
  print("Extending actuator...")
  GPIO.output(RELAY_1, GPIO.LOW)  # Turn Relay 1 ON
  GPIO.output(RELAY_2, GPIO.HIGH)  # Keep Relay 2 OFF
  time.sleep(5)  # Run for 5 seconds

  # Stop / Hold
  print("Stopping...")
  GPIO.output(RELAY_1, GPIO.HIGH)
  GPIO.output(RELAY_2, GPIO.HIGH)
  time.sleep(2)

  # 2. Retract the Actuator
  print("Retracting actuator...")
  GPIO.output(RELAY_1, GPIO.HIGH)  # Keep Relay 1 OFF
  GPIO.output(RELAY_2, GPIO.LOW)  # Turn Relay 2 ON
  time.sleep(5)  # Run for 5 seconds

  # Stop / Hold
  print("Stopping...")
  GPIO.output(RELAY_1, GPIO.HIGH)
  GPIO.output(RELAY_2, GPIO.HIGH)

  print("Test completed successfully.")

except KeyboardInterrupt:
  print("\nTest interrupted by user.")

finally:
  # Clean up GPIO safely on exit
  GPIO.output(RELAY_1, GPIO.HIGH)
  GPIO.output(RELAY_2, GPIO.HIGH)
  GPIO.cleanup()
  print("GPIO cleaned up.")