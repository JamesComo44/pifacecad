#!/usr/bin/env python3
import argparse

from pifacecad import PiFaceCAD
from programs.clear import clear_lcd


def write(cad: PiFaceCAD, message: str):
    clear_lcd(cad)
    cad.lcd.write(message)


def write_with_backlight(cad: PiFaceCAD, message: str):
    write(cad, message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write a message to the LCD screen.")
    parser.add_argument(
        "message", 
        type=str,
        nargs="?",
        default="",
        help="Text to display on LCD screen. If unset, clears the LCD screen.",
    )

    args = parser.parse_args()

    cad = PiFaceCAD()
    write(cad, args.message)
