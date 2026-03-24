"""
boot.py – MicroPython boot file for InkyPi ESP32.

This file runs automatically before main.py.  It attempts to connect
to Wi-Fi using the saved credentials.  If that fails it starts the
device as an Access Point so the user can configure Wi-Fi through the
web interface.

The Wi-Fi state is stored in module-level variables so main.py can
read them without repeating the connection logic.
"""

import config_manager
import wifi_manager

# Load persisted configuration
cfg = config_manager.load()

# ------------------------------------------------------------------
# Try to connect as a station
# ------------------------------------------------------------------
print("InkyPi ESP32 – booting …")

ssid = cfg.get("wifi_ssid", "")
password = cfg.get("wifi_password", "")

if ssid:
    print(f"Connecting to Wi-Fi network: {ssid} …")
    ip = wifi_manager.connect_sta(ssid, password)
    if ip:
        print(f"Connected. IP address: {ip}")
    else:
        print("Failed to connect to Wi-Fi. Starting Access Point …")
        ap_ip = wifi_manager.start_ap(
            cfg.get("ap_ssid", "InkyPi-ESP32"),
            cfg.get("ap_password", "inkypi123"),
        )
        print(f"AP started. Connect to '{cfg.get('ap_ssid', 'InkyPi-ESP32')}' "
              f"and open http://{ap_ip}")
else:
    print("No Wi-Fi credentials stored. Starting Access Point …")
    ap_ip = wifi_manager.start_ap(
        cfg.get("ap_ssid", "InkyPi-ESP32"),
        cfg.get("ap_password", "inkypi123"),
    )
    print(f"AP started. Connect to '{cfg.get('ap_ssid', 'InkyPi-ESP32')}' "
          f"and open http://{ap_ip}")
