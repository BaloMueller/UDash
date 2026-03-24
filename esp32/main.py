"""
main.py – Main application for InkyPi ESP32.

Responsibilities
----------------
1. Initialise the e-paper display.
2. Start the HTTP server in a background thread so the device can be
   configured or receive images via HTTP at any time.
3. Periodically poll the InkyPi Raspberry Pi server for the latest
   display image and push it to the e-paper.

The polling loop fetches:

    GET <inkypi_url>/api/esp32/image_data?display_type=<display_type>

The server returns raw 1-bit-per-pixel image data (see
src/blueprints/main.py for the endpoint implementation).

If the device is in AP mode (not yet connected to Wi-Fi) the polling
loop is skipped and only the HTTP configuration server runs.
"""

import time
import _thread
import gc
import config_manager
import wifi_manager
from epaper_display import EPaperDisplay, DISPLAY_SPECS
from http_server import HTTPServer

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _fetch_image(url):
    """
    Fetch raw image data from the InkyPi server.

    Uses MicroPython's built-in socket module directly so that we do not
    need urequests (which buffers the whole response in RAM).

    Returns (bytes, width, height) on success, or (None, 0, 0) on failure.
    """
    import socket

    # Parse URL  –  only http:// is supported
    if url.startswith("http://"):
        url = url[7:]
    elif url.startswith("https://"):
        print("HTTPS not supported; using HTTP instead")
        url = url[8:]

    if "/" in url:
        host, path = url.split("/", 1)
        path = "/" + path
    else:
        host = url
        path = "/"

    port = 80
    if ":" in host:
        host, port_str = host.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            pass

    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket()
        s.settimeout(10)
        s.connect(addr)

        request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        s.sendall(request.encode())

        # Read response headers
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = s.recv(256)
            if not chunk:
                break
            raw += chunk

        header_end = raw.index(b"\r\n\r\n")
        header_bytes = raw[:header_end].decode(errors="replace")
        body_start = raw[header_end + 4:]

        # Parse status code
        first_line = header_bytes.split("\r\n")[0]
        status_code = int(first_line.split()[1])
        if status_code != 200:
            print(f"Server returned HTTP {status_code}")
            return None, 0, 0

        # Parse width/height from response headers
        width = 0
        height = 0
        for line in header_bytes.split("\r\n")[1:]:
            lower = line.lower()
            if lower.startswith("x-width:"):
                try:
                    width = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif lower.startswith("x-height:"):
                try:
                    height = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

        # Read remainder of body
        data = bytearray(body_start)
        while True:
            chunk = s.recv(512)
            if not chunk:
                break
            data.extend(chunk)

        s.close()
        return bytes(data), width, height

    except Exception as exc:
        print(f"Fetch error: {exc}")
        return None, 0, 0


def _polling_loop(display, config):
    """Run forever: fetch image from InkyPi server and push to display."""
    while True:
        try:
            if not wifi_manager.is_connected():
                time.sleep(5)
                continue

            base_url = config.get("inkypi_url", "").rstrip("/")
            display_type = config.get("display_type", "epd2in13v2")
            url = f"{base_url}/api/esp32/image_data?display_type={display_type}"

            print(f"Polling: {url}")
            data, width, height = _fetch_image(url)
            gc.collect()

            if data and width and height:
                expected = ((width + 7) // 8) * height
                if len(data) == expected:
                    print(f"Displaying {width}x{height} image ({len(data)} bytes)")
                    display.display(data)
                else:
                    print(f"Unexpected data size: {len(data)} (expected {expected})")
            else:
                print("No valid image data received")

        except Exception as exc:
            print(f"Polling error: {exc}")

        interval = config.get("refresh_interval", 300)
        time.sleep(interval)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


def main():
    config = config_manager.load()

    # Initialise e-paper display
    display_type = config.get("display_type", "epd2in13v2")
    try:
        display = EPaperDisplay(display_type=display_type,
                                rotation=config.get("rotation", 0))
        display.init()
        display.clear()
        print(f"Display '{display_type}' initialised "
              f"({display.width}x{display.height})")
    except Exception as exc:
        print(f"Display init failed: {exc}")
        display = None

    def save_and_reboot(cfg):
        config_manager.save(cfg)
        import machine
        time.sleep(1)
        machine.reset()

    # Start HTTP server in a background thread
    server = HTTPServer(
        config=config,
        display=display,
        save_config=config_manager.save,
        on_reboot=lambda: save_and_reboot(config),
    )
    _thread.start_new_thread(server.serve_forever, ())
    print("HTTP config server started")

    # Start polling loop (only useful when connected to Wi-Fi)
    if display is not None and wifi_manager.is_connected():
        _polling_loop(display, config)
    else:
        # Just keep the main thread alive so the HTTP server thread stays up
        while True:
            time.sleep(60)


main()
