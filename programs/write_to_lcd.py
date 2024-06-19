#!/usr/bin/env python3
import argparse

from pifacecad import PiFaceCAD
from programs.clear import clear_lcd


def write(cad: PiFaceCAD, message: str):
    clear_lcd(cad)
    cad.lcd.write(message)


def write_with_backlight(cad: PiFaceCAD, message: str):
    cad.lcd.backlight_on()
    write(cad, message)


def write_without_backlight(cad: PiFaceCAD, message: str):
    cad.lcd.backlight_off()
    write(cad, message)


def main():
    parser = argparse.ArgumentParser(description="Write a message to the LCD screen.")
    parser.add_argument(
        "message",
        type=str,
        nargs="?",
        default="",
        help="Text to display on LCD screen. If unset, clears the LCD screen.",
    )
    parser.add_argument(
        "--no-backlight",
        "-nb",
        action="store_true",
        help="Write the message without the backlight off. Turns it off if already on.",
    )

    args = parser.parse_args()
    cad = PiFaceCAD()

    if args.no_backlight:
        write_without_backlight(cad, args.message)
    else:
        write_with_backlight(cad, args.message)


if __name__ == "__main__":
    main()
