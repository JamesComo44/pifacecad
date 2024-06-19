#!/usr/bin/env python3

import pifacecad

def main():
    cad = pifacecad.PiFaceCAD()

    cad.lcd.blink_off()
    cad.lcd.cursor_off()

    cad.lcd.backlight_on()
    cad.lcd.write("I'm Gay!")

if __name__ == "__main__":
    main()

