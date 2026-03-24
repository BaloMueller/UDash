"""
wifi_manager.py – Wi-Fi connection helper for InkyPi ESP32.

Tries to connect in Station mode using saved credentials.
Falls back to Access-Point mode so the user can configure Wi-Fi via
the built-in HTTP server.
"""

import network
import time

# How long (seconds) to wait for STA association
_STA_TIMEOUT = 15


def connect_sta(ssid, password):
    """
    Try to connect as a Wi-Fi station.

    Returns the assigned IP address on success, or None on failure.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan.ifconfig()[0]

    wlan.connect(ssid, password)
    deadline = time.time() + _STA_TIMEOUT
    while not wlan.isconnected():
        if time.time() > deadline:
            wlan.active(False)
            return None
        time.sleep(0.5)

    return wlan.ifconfig()[0]


def start_ap(ssid, password):
    """
    Start the device as a Wi-Fi Access Point.

    Returns the AP IP address (always 192.168.4.1 on MicroPython).
    """
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    # authmode 3 = WPA2-PSK; use 0 for open network when no password given
    authmode = 3 if password else 0
    ap.config(essid=ssid, password=password, authmode=authmode)
    # Wait until the interface is ready
    while not ap.active():
        time.sleep(0.2)
    return ap.ifconfig()[0]


def stop_ap():
    """Deactivate the AP interface."""
    ap = network.WLAN(network.AP_IF)
    ap.active(False)


def is_connected():
    """Return True when the STA interface has an IP address."""
    wlan = network.WLAN(network.STA_IF)
    return wlan.isconnected()


def get_ip():
    """Return the current STA IP address, or None if not connected."""
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan.ifconfig()[0]
    return None
