import time
import lgpio

# Configuration
SERVO_PIN = 18  # Broadcom pin 18 (Physical Pin 12)
PWM_FREQ = 50  # Standard hobby servo frequency is 50Hz

# DS3235 pulse width ranges (in milliseconds)
# Standard: 0.5ms (0°) to 2.5ms (180°)
MIN_WIDTH_MS = 0.5
MAX_WIDTH_MS = 2.5
PERIOD_MS = 1000.0 / PWM_FREQ  # 20ms for 50Hz


def angle_to_duty_cycle(angle):
  """Converts an angle (0 to 180) to a duty cycle percentage."""
  angle = max(0, min(180, angle))  clamp angle
  pulse_ms = MIN_WIDTH_MS + (angle / 180.0) * (MAX_WIDTH_MS - MIN_WIDTH_MS)
  duty_cycle = (pulse_ms / PERIOD_MS) * 100.0
  return duty_cycle


# Initialize lgpio chip handle (0 is the default chip for Pi 5)
h = lgpio.gpiochip_open(0)

try:
  print(
      "Starting RGS/DS3235 35kg Servo Test on Raspberry Pi 5. Press Ctrl+C to"
      " exit."
  )

  # Setup hardware PWM: frequency in Hz, initial duty cycle (0%)
  lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, 0)

  while True:
    # Move to 0 degrees
    print("Moving to 0°")
    lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, angle_to_duty_cycle(0))
    time.sleep(1.5)

    # Move to 90 degrees (Center)
    print("Moving to 90° (Center)")
    lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, angle_to_duty_cycle(90))
    time.sleep(1.5)

    # Move to 180 degrees
    print("Moving to 180°")
    lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, angle_to_duty_cycle(180))
    time.sleep(1.5)

    # Sweep test smoothly
    print("Sweeping...")
    for angle in range(0, 181, 5):
      lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, angle_to_duty_cycle(angle))
      time.sleep(0.03)

    for angle in range(180, -1, -5):
      lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, angle_to_duty_cycle(angle))
      time.sleep(0.03)

except KeyboardInterrupt:
  print("\nStopping script...")

finally:
  # Turn off PWM and close chip connection safely
  lgpio.tx_pwm(h, SERVO_PIN, PWM_FREQ, 0)
  lgpio.gpiochip_close(h)
  print("GPIO cleaned up.")