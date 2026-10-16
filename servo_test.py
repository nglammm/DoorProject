from time import sleep
from gpiozero import AngularServo

# Setup parameters for DS3235 35kg Servo
# pin=18 corresponds to BCM GPIO 18 (Physical Pin 12)
# min_pulse_width = 0.5ms (0.0005s), max_pulse_width = 2.5ms (0.0025s)
servo = AngularServo(
    18, min_angle=0, max_angle=180, min_pulse_width=0.5 / 1000, max_pulse_width=2.5 / 1000
)

try:
  print("Starting AngularServo test for 35kg servo. Press Ctrl+C to exit.")

  while True:
    print("Moving to 0°")
    servo.angle = 0
    sleep(1.5)

    print("Moving to 90° (Center)")
    servo.angle = 90
    sleep(1.5)

    print("Moving to 180°")
    servo.angle = 180
    sleep(1.5)

    # Smooth sweep demo using AngularServo
    print("Sweeping smoothly...")
    for angle in range(0, 181, 10):
      servo.angle = angle
      sleep(0.05)

    for angle in range(180, -1, -10):
      servo.angle = angle
      sleep(0.05)

except KeyboardInterrupt:
  print("\nStopping test. Detaching servo.")
  # Detaching sets the pulse to None, dropping the PWM signal so the servo relaxes
  servo.detach()