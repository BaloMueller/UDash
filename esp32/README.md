# InkyPi – ESP32 Wi-Fi Port

This directory contains a **MicroPython** port of InkyPi for ESP32 microcontrollers.  
An ESP32 with an attached e-paper display can act as a **thin Wi-Fi display client**
that fetches images from an InkyPi Raspberry Pi server (or any HTTP host) and renders
them on a connected e-paper screen—all with a sub-1 W power budget.

---

## Architecture

```
┌──────────────────────────────────┐          Wi-Fi / LAN
│  Raspberry Pi running InkyPi     │  ─────────────────────────────►  ESP32
│  (plugin system, web UI, etc.)   │  GET /api/esp32/image_data        │
│                                  │  ◄──────── raw 1-bit image ───────┤
└──────────────────────────────────┘                                   │
                                                                       ▼
                                                            e-paper display (SPI)
```

The Pi does all the heavy lifting (plugin rendering, scheduling, web UI).  
The ESP32 simply polls for the latest image and pushes it to the display.

---

## Supported Hardware

### Microcontroller
- **ESP32** (any variant with at least 4 MB flash and 520 KB SRAM)
  - Tested with: ESP32-WROOM-32, ESP32-S3, Waveshare ESP32 e-Paper Driver Board

### E-Paper Displays (via SPI)
| `display_type` | Model | Resolution |
|---|---|---|
| `epd2in13v2` | Waveshare 2.13" v2 | 250 × 122 px |
| `epd2in9v2`  | Waveshare 2.9" v2  | 296 × 128 px |
| `epd4in2`    | Waveshare 4.2"     | 400 × 300 px |

> **Note:** Only black-and-white (BW) SSD1680/UC8176-based displays are supported.
> Colour e-paper and IT8951-based displays are not currently supported.

### Default GPIO Wiring (Waveshare ESP32 Driver Board)
| Signal | ESP32 GPIO |
|--------|-----------|
| SCK    | 13        |
| MOSI   | 14        |
| CS     | 15        |
| DC     | 27        |
| RST    | 26        |
| BUSY   | 25        |

---

## Quick Start

### 1. Flash MicroPython to the ESP32

Download the latest stable MicroPython firmware from
[micropython.org/download/esp32](https://micropython.org/download/esp32/) and flash it:

```bash
pip install esptool
esptool.py --chip esp32 erase_flash
esptool.py --chip esp32 --baud 460800 write_flash -z 0x1000 esp32-*.bin
```

### 2. Copy files to the ESP32

Use [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html) or
[Thonny](https://thonny.org) to copy all files from this directory to the root of the
ESP32 filesystem:

```bash
pip install mpremote
cd esp32/
mpremote cp boot.py main.py config_manager.py wifi_manager.py \
           epaper_display.py http_server.py :
```

### 3. Create the initial configuration

Copy `example_config.json` to `config.json` and edit your Wi-Fi credentials:

```bash
cp example_config.json config.json
# Edit config.json then upload it:
mpremote cp config.json :
```

Or skip this step and configure Wi-Fi through the web interface (see step 5).

### 4. Connect the e-paper display

Wire your display according to the GPIO table above.  If you are using the
[Waveshare ESP32 e-Paper Driver Board](https://www.waveshare.com/wiki/E-Paper_ESP32_Driver_Board)
the connections are already made on the PCB.

### 5. First boot

Reset the ESP32.  If valid Wi-Fi credentials are saved it will connect automatically.
Otherwise it starts an Access Point named **InkyPi-ESP32** (password: `inkypi123`).

1. Connect your phone or laptop to the **InkyPi-ESP32** network.
2. Open **http://192.168.4.1** in a browser.
3. Enter your Wi-Fi credentials and the URL of your InkyPi Pi server.
4. Click **Save & Reboot**.

After the reboot the ESP32 connects to your network and begins polling the InkyPi
server at the configured interval.

---

## Configuration Reference

`config.json` fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `wifi_ssid` | string | `""` | Wi-Fi network name |
| `wifi_password` | string | `""` | Wi-Fi password |
| `inkypi_url` | string | `"http://inkypi.local"` | Base URL of the InkyPi Pi server |
| `display_type` | string | `"epd2in13v2"` | E-paper model (see table above) |
| `refresh_interval` | int | `300` | Seconds between image polls |
| `ap_ssid` | string | `"InkyPi-ESP32"` | Hotspot name shown when not connected |
| `ap_password` | string | `"inkypi123"` | Hotspot password |
| `rotation` | int | `0` | Display rotation: 0, 90, 180 or 270 |

---

## Pushing Images Directly to the ESP32

In addition to polling the Pi server, the ESP32 HTTP server accepts images pushed
directly to it:

```
POST http://<esp32-ip>/display
Content-Type: application/octet-stream
X-Width: 250
X-Height: 122

<raw 1-bit-per-pixel data, row-major, MSB first>
```

This allows any application on the local network to display arbitrary content on the
e-paper without the Pi acting as an intermediary.

---

## InkyPi Pi Server – ESP32 Endpoint

The Pi-side endpoint `/api/esp32/image_data` was added to `src/blueprints/main.py`.

```
GET /api/esp32/image_data?display_type=epd2in13v2
```

| Parameter | Description |
|---|---|
| `display_type` | One of the supported display types (derives width/height automatically) |
| `width` + `height` | Explicit pixel dimensions (used when `display_type` is omitted) |

**Response:** `application/octet-stream` containing a raw 1-bit-per-pixel monochrome
bitmap, row-major, MSB first (1 = white, 0 = black).  
Response headers `X-Width` and `X-Height` carry the bitmap dimensions.

---

## File Overview

| File | Purpose |
|---|---|
| `boot.py` | MicroPython boot file: connects to Wi-Fi or starts AP |
| `main.py` | Main loop: polls Pi server + drives display; starts HTTP server thread |
| `wifi_manager.py` | STA / AP Wi-Fi helpers |
| `config_manager.py` | Read / write `config.json` on the ESP32 filesystem |
| `epaper_display.py` | SPI e-paper driver (SSD1680 / UC8176 compatible) |
| `http_server.py` | Single-threaded HTTP server (config UI + image push endpoint) |
| `example_config.json` | Configuration template |

---

## Limitations & Future Work

- Only **black-and-white** e-paper displays are supported today.
- HTTPS is not supported on the ESP32 side; ensure InkyPi is reachable over HTTP on
  your local network.
- The polling loop runs in the main thread; true concurrent refresh requires
  `uasyncio` (planned).
- Only the current displayed image is mirrored; playlist scheduling remains on the Pi.
