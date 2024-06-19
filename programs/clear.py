#!/usr/bin/env python3
import argparse

from pifacecad import PiFaceCAD


def clear_lcd(cad: PiFaceCAD):
    cad.lcd.blink_off()
    cad.lcd.cursor_off()
    cad.lcd.clear()


def turn_off_lcd(cad: PiFaceCAD):
    cad.lcd.display_off()
    cad.lcd.backlight_off()


def main():
    parser = argparse.ArgumentParser(description="Clear the LCD screen.")
    parser.add_argument(
        "-f",
        "--off",
        action="store_true",
        help="Turns the LCD screen off after clearing it.",
    )

    args = parser.parse_args()
    cad = PiFaceCAD()

    if args.off:
        turn_off_lcd(cad)

    clear_lcd(cad)


if __name__ == "__main__":
    main()
