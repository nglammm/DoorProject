from time import sleep
from gpiozero import AngularServo, OutputDevice

servo = AngularServo(
    18, min_angle=0, max_angle=180, min_pulse_width=0.5 / 1000, max_pulse_width=2.5 / 1000
)

try:
    print("Starting AngularServo test. Press Ctrl+C to exit.")
    while True:
        #Narrow the extremes slightly first to rule out physical end-stop stalling
        servo.angle = 10
        sleep(1.5)
        servo.angle = 90
        sleep(1.5)
        servo.angle = 170
        sleep(1.5)

except KeyboardInterrupt:
    print("\nStopping test. Detaching servo and pulling signal LOW.")
    servo.detach()
    sleep(0.2)  # Give the servo MCU time to register 0 pulse width
    servo.close()  # Release the pin from AngularServo
    
    # Actively hold GPIO 18 LOW (0V) so it doesn't float
    pin_killer = OutputDevice(18, initial_value=False)
    sleep(0.5)