from gpiozero import DigitalOutputDevice, Button
from signal import pause


# Most 3-pin modules have an internal pull-down resistor, meaning OUT goes HIGH when pressed.
# pull_up=False configures the input to expect an active-HIGH signal.
btn = Button(22, pull_up=False)

def on_press():
    print("Button pressed!")

def on_release():
    print("Button released!")

btn.when_pressed = on_press
btn.when_released = on_release

print("Button ready. Press Ctrl+C to exit.")
pause()