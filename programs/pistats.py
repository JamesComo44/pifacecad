#!/usr/bin/env python3
import signal
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier, BrokenBarrierError

import requests
from pifacecad import IODIR_ON, PiFaceCAD, SwitchEventListener

from clear import clear_lcd, turn_on_lcd


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


class StatusDriver:
    def __init__(self):
        self.cad = PiFaceCAD()
        init_lcd(self.cad)

        self.stats = pihole_stats()
        self.uptime = uptime()
        self.render_status_ads_blocked()

    def update(self):
        self.status = pihole_stats()
        self.uptime = uptime()

    def render_uptime_ip(self, event=None):
        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)

        self.cad.lcd.write(f"Up:{self.uptime}")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write(f"IP:{self.stats.ip_address}")

    def render_status_ads_blocked(self, event=None):
        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)

        self.cad.lcd.write(f"Pihole {self.stats.status.title()}")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write(
            f"Ads:{self.stats.percentage_blocked:.1f}% {self.stats.ads_blocked}"
        )

    def render_domains_blocked(self, event=None):
        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)

        self.cad.lcd.write("Domains Blocked")
        toggle_cursor_line(self.cad)
        self.cad.lcd.write(self.stats.domains_blocked)

    def render_client_info(self, event=None):
        clear_lcd(self.cad)
        toggle_cursor_line(self.cad, reset=True)

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

    driver = StatusDriver()

    global end_barrier
    end_barrier = Barrier(2)
    signal.signal(signal.SIGINT, signal_exit_handler)

    switchlistener = SwitchEventListener(chip=driver.cad)
    switchlistener.register(0, IODIR_ON, driver.render_status_ads_blocked)
    switchlistener.register(1, IODIR_ON, driver.render_domains_blocked)
    switchlistener.register(2, IODIR_ON, driver.render_uptime_ip)
    switchlistener.register(3, IODIR_ON, driver.render_client_info)
    switchlistener.register(4, IODIR_ON, end_barrier.wait)

    switchlistener.activate()

    try:
        print("Loading complete. Waiting for user input or SIGINT")
        end_barrier.wait()
    except BrokenBarrierError:
        print("Barrier broken. Exiting Threads")
    except SystemExit:
        print("Exiting Program")
    finally:
        switchlistener.deactivate()


if __name__ == "__main__":
    main()
