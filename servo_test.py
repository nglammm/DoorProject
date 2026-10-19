from time import sleep
from gpiozero import AngularServo, OutputDevice

# 1. Setup Relay on BCM GPIO 17 (Physical Pin 11)
# Note: Most 5V relay modules are Active-Low (active_high=False).
# If your relay turns OFF when it should be ON, change active_high to True.
relay = OutputDevice(17, active_high=False, initial_value=False)

# 2. Setup RDS3235 Servo on BCM GPIO 18 (Physical Pin 12)
# initial_angle=None keeps PWM off until the relay powers up the servo
servo = AngularServo(
    18,
    initial_angle=None,
    min_angle=0,
    max_angle=180,
    min_pulse_width=0.5 / 1000,
    max_pulse_width=2.5 / 1000,
)

try:
    print("Turning relay ON (GPIO 17)...")
    relay.on()
    sleep(0.5)  # Give the servo's internal controller half a second to boot

    print("Starting RDS3235 movement test. Press Ctrl+C to stop and cut power.")
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

        print("Sweeping smoothly...")
        for angle in range(0, 181, 10):
            servo.angle = angle
            sleep(0.05)

        for angle in range(180, -1, -10):
            servo.angle = angle
            sleep(0.05)

except KeyboardInterrupt:
    print("\nCtrl+C detected! Detaching PWM and cutting relay power...")
    
    # 1. Stop PWM signal first so GPIO 18 doesn't backfeed into an unpowered servo
    servo.detach()
    sleep(0.1)
    
    # 2. Cut power via relay
    relay.off()
    print("Relay is now OFF. Listen to verify the servo hum has completely stopped.")
    
    # Hold for 3 seconds before exiting so you can distinguish script-controlled 
    # relay state from Raspberry Pi GPIO cleanup on exit
    sleep(3)
    print("Exiting cleanly.")