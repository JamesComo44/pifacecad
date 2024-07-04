#!/usr/bin/env python3
import re
import signal
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from subprocess import check_output
from threading import Barrier, BrokenBarrierError, Timer

import requests
from pifacecad import IODIR_ON, LCDBitmap, PiFaceCAD, SwitchEventListener
from pifacecad.tools.question import LCDQuestion

from clear import clear_lcd, turn_off_lcd, turn_on_lcd


@dataclass
class PiHoleStats:
    """
    Blocked data is for current day (today).
    """

    status: str
    ip_address: str
    ads_blocked: int
    percentage_blocked: float
    domains_blocked: str
    dns_queries: int
    clients: int


def pihole_stats() -> PiHoleStats:
    ip_address = _get_ip_address()
    raw_stats = _raw_api_stats(ip_address)

    return PiHoleStats(
        raw_stats["status"],
        ip_address,
        int(raw_stats["ads_blocked_today"]),
        float(raw_stats["ads_percentage_today"]),
        raw_stats["domains_being_blocked"],
        int(raw_stats["dns_queries_today"]),
        int(raw_stats["unique_clients"]),
    )


def _raw_api_stats(ip_address: str) -> dict:
    token = _get_token()
    response = requests.get(f"http://{ip_address}/admin/api.php?summary&auth={token}")
    response.raise_for_status()
    return response.json()


def _get_token():
    location = Path("/etc/pihole/setupVars.conf")

    if not location.is_file():
        raise RuntimeError("Error: setupVars.conf not found!")

    with open(location, "r") as file:
        for line in file:
            if line.startswith("WEBPASSWORD="):
                return line.strip().split("=")[1]

    raise RuntimeError("Error: Count not find token in setupVars.conf!")


def _get_ip_address() -> str:
    try:
        with _create_socket() as soc:
            soc.connect(("8.8.8.8", 80))
            ip_address = soc.getsockname()[0]
    except (socket.gaierror, socket.herror) as exec:
        print("Error getting IP Address! {}".format(exec))
        ip_address = "ERROR?"

    return ip_address


@contextmanager
def _create_socket():
    new_socket = None

    try:
        new_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        yield new_socket
    except (socket.error, socket.gaierror, socket.herror) as exec:
        print("Socket error occurred: {}".format(exec))
        raise
    finally:
        if new_socket:
            new_socket.close()


def uptime():
    contents = "NaN"

    with open("/proc/uptime", mode="r") as file:
        # [<seconds> <???>]
        contents = file.read().split()

    total_seconds = float(contents[0])

    minute = 60
    hour = minute * 60
    day = hour * 24

    days = int(total_seconds / day)
    hours = int((total_seconds % day) / hour)
    minutes = int((total_seconds % hour) / minute)

    return f"{days}D {hours}H {minutes}M"


def run_shell(command) -> str:
    return check_output(command, shell=True).decode("utf-8")


def memory_usage_percent() -> str:
    total_memory = run_shell("free | grep 'Mem' | awk '{print $2}'")
    used_memory = run_shell("free | grep 'Mem' | awk '{print $3}'")

    used_percentage = float(used_memory) / float(total_memory)
    return f"{used_percentage:.1}%"


def current_temperature() -> str:
    return run_shell("/usr/bin/vcgencmd measure_temp | awk -F'=' '{print $2}'")


def pihole_updates_available() -> bool:
    pattern = r"v(\d+\.\d+\.\d+)\s+\(Latest:\s+v(\d+\.\d+\.\d+)\)"
    matches = re.findall(pattern, run_shell("pihole -v"))

    for current, latest in matches:
        if current != latest:
            print(f"Pihole update available. Current: {current} - Latest {latest}")
            return True

    return False


def dietpi_updates_available() -> bool:
    """
    https://github.com/Fourdee/DietPi/blob/master/dietpi/func/dietpi-banner
    """
    if Path("/run/dietpi/.update_available").exists():
        return True

    if Path("/run/dietpi/.live_patches").exists():
        return True

    return False


def apt_updates_available() -> bool:
    if Path("/run/dietpi/.apt_updates").exists():
        return True

    return False


def any_updates_available() -> bool:
    updates = [
        dietpi_updates_available(),
        pihole_updates_available(),
        apt_updates_available()
    ]
    return any(updates)


class StatusDriver:
    def __init__(self):
        self.cad = PiFaceCAD()
        init_lcd(self.cad)

        self.memory_symbol_index = 0
        self.cad.lcd.store_custom_bitmap(
            self.memory_symbol_index,
            LCDBitmap([0xE, 0x1F, 0xE, 0x1F, 0xE, 0x1F, 0xE, 0x0]),
        )

        self.temperature_symbol_index = 1
        self.cad.lcd.store_custom_bitmap(
            self.temperature_symbol_index,
            LCDBitmap([0x4, 0xA, 0xA, 0xA, 0x11, 0x1F, 0xE, 0x0]),
        )

        self.ip_symbol_index = 2
        self.cad.lcd.store_custom_bitmap(
            self.ip_symbol_index,
            LCDBitmap(
                [0x1C, 0x8, 0x8, 0x1C, 0x7, 0x5, 0x7, 0x4],
            ),
        )

        self._backlight_on = True
        self._update_interval_min = 30
        self._current_render_page_index = 0
        self._auto_rotate_page = True

        self.stats = ""
        self.uptime = ""
        self.memory = ""
        self.temperature = ""

        self.update()

        self.update_timer = Timer(self._update_interval_min * 60, self.auto_update)
        self.update_timer.start()

        self.render_status_ip()

    def choose_function(self, event=None):
        self.cancel_timers()

        backlight_text = "Backlight Off" if self._backlight_on else "Backlignt On"
        rotate_text = "Rotate Off" if self._auto_rotate_page else "Rotate On"
        interval_text = f"Interval {self._update_interval_min}min"

        question = LCDQuestion(
            question="Choose Function",
            answers=[
                backlight_text,
                interval_text,
                rotate_text,
                "Update Software",
                "Nothing",
            ],
            selector=">",
            cad=self.cad,
        )

        answer_index = question.ask()

        if answer_index == 0:
            self.toggle_backlight()

        if answer_index == 1:
            self.update_interval()
            return

        if answer_index == 2:
            self._auto_rotate_page = not self._auto_rotate_page

        if answer_index == 3:
            self.update_software()
            return

        self.auto_update()

    def update_software(self, event=None):
        self.cancel_timers()

        dietpi_update = dietpi_updates_available()
        apt_update = apt_updates_available()
        pihole_update = pihole_updates_available()

        update_modules = []

        if dietpi_update:
            update_modules.append("OS")
        if apt_update:
            update_modules.append("APT")
        if pihole_update:
            update_modules.append("PI")

        if update_modules:
            update_question = "Update " + "+".join(update_modules)
        else:
            update_question = "No Updates"

        question = LCDQuestion(
            question=update_question,
            answers=["No", "Yes"],
            selector=">" if update_modules else "Check? >",
            cad=self.cad,
        )

        should_update = question.ask()

        if not should_update:
            self.auto_update()
            return

        print(f"Updating Software {update_modules} ...")

        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)
        self.cad.lcd.write("Updating...")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write("Do not unplug!")

        if apt_update:
            run_shell("apt update")
            run_shell("apt upgrade")

        if pihole_update:
            run_shell("pihole -up")

        if dietpi_update:
            run_shell("dietpi-update 1")

        print("Updates Complete!")
        self.auto_update(load_last_page = True)

    def update(self):
        self.stats = pihole_stats()
        self.uptime = uptime()
        self.memory = memory_usage_percent()
        self.temperature = current_temperature()

        if any_updates_available():
            self.stats.status = "updates!"

    def auto_update(self, load_last_page = False):
        if self._update_interval_min == 0:
            return

        print("Auto updating display data")
        self.update()

        if self._auto_rotate_page and not load_last_page:
            self._current_render_page_index += 1

            if self._current_render_page_index > 3:
                self._current_render_page_index = 0

        self.update_timer = Timer(self._update_interval_min * 60, self.auto_update)
        self.update_timer.start()

        if self._current_render_page_index == 0:
            self.render_status_ip()
        if self._current_render_page_index == 1:
            self.render_uptime_memory_temp()
        if self._current_render_page_index == 2:
            self.render_blocked_info()
        if self._current_render_page_index == 3:
            self.render_client_info()

    def cancel_timers(self):
        if self.update_timer:
            self.update_timer.cancel()

    def update_interval(self, event=None):
        self.cancel_timers()

        intervals = ["1", "5", "10", "30", "60", "120", "240", "0"]

        question = LCDQuestion(
            question="Update Interval?",
            answers=intervals,
            selector="Minutes >",
            cad=self.cad,
        )

        answer_index = question.ask()
        self._update_interval_min = int(intervals[answer_index])
        self.auto_update()

    def toggle_backlight(self, event=None):
        self._backlight_on = not self._backlight_on

        if self._backlight_on:
            self.cad.lcd.backlight_on()
        else:
            self.cad.lcd.backlight_off()

    def render_status_ip(self, event=None):
        self._current_render_page_index = 0

        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)
        self.update()

        self.cad.lcd.write(f"Pihole {self.stats.status.title()}")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write_custom_bitmap(self.ip_symbol_index)
        self.cad.lcd.write(f":{self.stats.ip_address}")

    def render_uptime_memory_temp(self, event=None):
        self._current_render_page_index = 1

        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)
        self.update()

        self.cad.lcd.write(f"Up:{self.uptime}")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write_custom_bitmap(self.memory_symbol_index)
        self.cad.lcd.write(self.memory)

        self.cad.lcd.write(" ")

        self.cad.lcd.write_custom_bitmap(self.temperature_symbol_index)
        self.cad.lcd.write(self.temperature)

    def render_blocked_info(self, event=None):
        self._current_render_page_index = 2

        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)
        self.update()

        self.cad.lcd.write(
            f"Ads:{self.stats.percentage_blocked:.1f}% {self.stats.ads_blocked}"
        )
        toggle_cursor_line(self.cad)
        self.cad.lcd.write(f"Sites:{self.stats.domains_blocked}")

    def render_client_info(self, event=None):
        self._current_render_page_index = 3

        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)
        self.update()

        self.cad.lcd.write(f"Clients: {self.stats.clients}")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write(f"DNS: {self.stats.dns_queries}")


def toggle_cursor_line(cad: PiFaceCAD, reset=False):
    if reset:
        cad.lcd.home()
        return

    cursor_position = cad.lcd.get_cursor()

    if cursor_position[1] == 0:
        cad.lcd.set_cursor(0, 1)
        return

    cad.lcd.home()


def init_lcd(cad: PiFaceCAD):
    clear_lcd(cad)
    turn_on_lcd(cad)
    toggle_cursor_line(cad, reset=True)


def signal_exit_handler(sig, frame):
    print("SIGINT received, breaking barrier")
    end_barrier.abort()
    raise SystemExit


def main():
    print("Initializing Pihole Status...")

    global end_barrier
    end_barrier = Barrier(2)
    signal.signal(signal.SIGINT, signal_exit_handler)

    driver = StatusDriver()

    switchlistener = SwitchEventListener(chip=driver.cad)
    switchlistener.register(0, IODIR_ON, driver.render_status_ip)
    switchlistener.register(1, IODIR_ON, driver.render_blocked_info)
    switchlistener.register(2, IODIR_ON, driver.render_uptime_memory_temp)
    switchlistener.register(3, IODIR_ON, driver.render_client_info)
    switchlistener.register(4, IODIR_ON, driver.choose_function)
    switchlistener.activate()

    try:
        print("Loading complete. Waiting for user input or SIGINT")
        end_barrier.wait()
    except BrokenBarrierError:
        print("Barrier broken. Exiting Threads")
    except SystemExit:
        print("Exiting Program")
    finally:
        driver.cancel_timers()
        switchlistener.deactivate()
        clear_lcd(driver.cad)
        turn_off_lcd(driver.cad)


if __name__ == "__main__":
    main()
