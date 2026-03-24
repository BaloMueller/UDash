"""
http_server.py – Minimal HTTP server for InkyPi ESP32.

Provides:
  GET  /           – HTML configuration page
  GET  /status     – JSON device status
  POST /config     – Update configuration fields (URL-encoded form)
  POST /display    – Receive a raw mono image and push to the display
                     Body: application/octet-stream  (1-bit/px, row-major)
                     Required headers: X-Width, X-Height

The server handles one request at a time (single-threaded).
"""

import json
import socket
import gc

# Inline HTML for the configuration page so we don't need a filesystem template
_CONFIG_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InkyPi ESP32</title>
<style>
  body {{ font-family: sans-serif; max-width: 480px; margin: 2rem auto; padding: 0 1rem; }}
  h1   {{ font-size: 1.4rem; }}
  label{{ display: block; margin-top: 1rem; font-weight: bold; }}
  input{{ width: 100%; padding: .4rem; box-sizing: border-box; }}
  button{{ margin-top: 1.4rem; padding: .5rem 1.2rem; }}
  .note{{ color: #555; font-size: .85rem; margin-top: .3rem; }}
  .ok  {{ color: green; }}
  .err {{ color: red; }}
</style>
</head>
<body>
<h1>&#x1F5BC; InkyPi ESP32</h1>
<p>Status: <strong class="{status_class}">{status_text}</strong></p>
<form method="POST" action="/config">
  <label>Wi-Fi SSID
    <input name="wifi_ssid" value="{wifi_ssid}" required>
  </label>
  <label>Wi-Fi Password
    <input name="wifi_password" type="password" value="{wifi_password}">
  </label>
  <label>InkyPi Server URL
    <input name="inkypi_url" value="{inkypi_url}" placeholder="http://inkypi.local">
    <span class="note">Base URL of your Raspberry Pi InkyPi installation</span>
  </label>
  <label>Display Type
    <input name="display_type" value="{display_type}" placeholder="epd2in13v2">
    <span class="note">epd2in13v2 / epd2in9v2 / epd4in2</span>
  </label>
  <label>Refresh Interval (seconds)
    <input name="refresh_interval" type="number" min="30" value="{refresh_interval}">
  </label>
  <button type="submit">Save &amp; Reboot</button>
</form>
</body>
</html>
"""


def _parse_form(body):
    """Decode a URL-encoded form body into a dict."""
    result = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[_url_decode(k)] = _url_decode(v)
    return result


def _url_decode(s):
    """Minimal percent-decoding + plus-to-space."""
    s = s.replace("+", " ")
    parts = s.split("%")
    out = parts[0]
    for part in parts[1:]:
        try:
            out += chr(int(part[:2], 16)) + part[2:]
        except (ValueError, IndexError):
            out += "%" + part
    return out


def _read_headers(rfile):
    """Read HTTP headers from a socket file-like object.  Returns a dict."""
    headers = {}
    while True:
        line = rfile.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode()] = v.strip().decode()
    return headers


def _send_response(conn, status, content_type, body):
    if isinstance(body, str):
        body = body.encode()
    header = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    conn.sendall(header.encode() + body)


class HTTPServer:
    """
    Single-threaded HTTP server.

    Parameters
    ----------
    config      : dict   – live config dict (shared reference)
    display     : EPaperDisplay | None
    save_config : callable – called with the config dict to persist it
    on_reboot   : callable – called after a config POST to trigger reboot
    """

    def __init__(self, config, display=None, save_config=None, on_reboot=None):
        self._config = config
        self._display = display
        self._save_config = save_config or (lambda c: None)
        self._on_reboot = on_reboot or (lambda: None)

    def serve_forever(self, host="0.0.0.0", port=80):
        """Block and handle requests forever.

        Parameters
        ----------
        host : str
            Interface to bind on. Defaults to ``"0.0.0.0"`` (all interfaces)
            so the server is reachable both via the ESP32's Access-Point
            address (192.168.4.1) during initial setup *and* via the
            station IP once the device is associated to a Wi-Fi network.
            Callers that only need one interface can pass a specific IP.
        port : int
            TCP port to listen on (default 80).
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        print(f"HTTP server listening on {host}:{port}")

        while True:
            try:
                conn, addr = s.accept()
                self._handle(conn, addr)
            except Exception as exc:
                print("HTTP error:", exc)
            finally:
                gc.collect()

    # ------------------------------------------------------------------
    # Request dispatch
    # ------------------------------------------------------------------

    def _handle(self, conn, addr):
        try:
            rfile = conn.makefile("rb")
            request_line = rfile.readline().decode(errors="replace").strip()
            if not request_line:
                return
            parts = request_line.split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]
            headers = _read_headers(rfile)

            if method == "GET" and path in ("/", "/index.html"):
                self._handle_get_index(conn, headers)
            elif method == "GET" and path == "/status":
                self._handle_get_status(conn, headers)
            elif method == "POST" and path == "/config":
                content_length = int(headers.get("content-length", 0))
                body = rfile.read(content_length).decode(errors="replace")
                self._handle_post_config(conn, headers, body)
            elif method == "POST" and path == "/display":
                content_length = int(headers.get("content-length", 0))
                body = rfile.read(content_length)
                self._handle_post_display(conn, headers, body)
            else:
                _send_response(conn, "404 Not Found", "text/plain", "Not Found")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_get_index(self, conn, headers):
        import wifi_manager
        connected = wifi_manager.is_connected()
        html = _CONFIG_HTML.format(
            status_class="ok" if connected else "err",
            status_text="Connected – " + (wifi_manager.get_ip() or "") if connected else "Not connected (AP mode)",
            wifi_ssid=self._config.get("wifi_ssid", ""),
            wifi_password=self._config.get("wifi_password", ""),
            inkypi_url=self._config.get("inkypi_url", "http://inkypi.local"),
            display_type=self._config.get("display_type", "epd2in13v2"),
            refresh_interval=self._config.get("refresh_interval", 300),
        )
        _send_response(conn, "200 OK", "text/html; charset=utf-8", html)

    def _handle_get_status(self, conn, headers):
        import wifi_manager
        status = {
            "connected": wifi_manager.is_connected(),
            "ip": wifi_manager.get_ip(),
            "display_type": self._config.get("display_type"),
            "inkypi_url": self._config.get("inkypi_url"),
            "refresh_interval": self._config.get("refresh_interval"),
        }
        _send_response(conn, "200 OK", "application/json", json.dumps(status))

    def _handle_post_config(self, conn, headers, body):
        form = _parse_form(body)
        for key in ("wifi_ssid", "wifi_password", "inkypi_url",
                    "display_type", "refresh_interval"):
            if key in form:
                value = form[key]
                if key == "refresh_interval":
                    try:
                        value = int(value)
                    except ValueError:
                        value = 300
                self._config[key] = value
        self._save_config(self._config)
        _send_response(conn, "200 OK", "text/plain", "Saved. Rebooting…")
        self._on_reboot()

    def _handle_post_display(self, conn, headers, body):
        """Receive raw 1-bit image data and push to the e-paper display."""
        if self._display is None:
            _send_response(conn, "503 Service Unavailable", "text/plain",
                           "Display not initialised")
            return

        try:
            width = int(headers.get("x-width", self._display.width))
            height = int(headers.get("x-height", self._display.height))
        except ValueError:
            _send_response(conn, "400 Bad Request", "text/plain",
                           "Invalid X-Width / X-Height header")
            return

        expected = ((width + 7) // 8) * height
        if len(body) != expected:
            _send_response(
                conn, "400 Bad Request", "text/plain",
                f"Body length {len(body)} != expected {expected} "
                f"for {width}x{height} display",
            )
            return

        try:
            self._display.display(body)
            _send_response(conn, "200 OK", "text/plain", "Displayed")
        except Exception as exc:
            _send_response(conn, "500 Internal Server Error", "text/plain",
                           str(exc))
