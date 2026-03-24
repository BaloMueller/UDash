"""
epaper_display.py – SPI e-paper display driver for InkyPi ESP32.

Supports common Waveshare black-and-white displays via the standard
6-wire SPI interface (SCK, MOSI, CS, DC, RST, BUSY).

Supported display types
-----------------------
  epd2in13v2   –  250 × 122 px  (Waveshare 2.13" v2)
  epd2in9v2    –  296 × 128 px  (Waveshare 2.9"  v2)
  epd4in2      –  400 × 300 px  (Waveshare 4.2"       )

Default GPIO pin mapping (Waveshare ESP32 Driver Board)
-------------------------------------------------------
  SCK   → GPIO 13
  MOSI  → GPIO 14
  CS    → GPIO 15
  DC    → GPIO 27
  RST   → GPIO 26
  BUSY  → GPIO 25
"""

import time
from machine import Pin, SPI

# ---------------------------------------------------------------------------
# Display geometry for supported models
# ---------------------------------------------------------------------------
DISPLAY_SPECS = {
    "epd2in13v2": {"width": 250, "height": 122},
    "epd2in9v2":  {"width": 296, "height": 128},
    "epd4in2":    {"width": 400, "height": 300},
}

# Default pin numbers (override via constructor kwargs)
_DEFAULT_PINS = {
    "sck":  13,
    "mosi": 14,
    "cs":   15,
    "dc":   27,
    "rst":  26,
    "busy": 25,
}

# SPI commands common to SSD1680 / UC8176 controllers
_CMD_DRIVER_OUTPUT_CTRL    = 0x01
_CMD_DATA_ENTRY_MODE        = 0x11
_CMD_SW_RESET               = 0x12
_CMD_TEMP_SENSOR_CTRL       = 0x18
_CMD_MASTER_ACTIVATION      = 0x20
_CMD_DISPLAY_UPDATE_CTRL2   = 0x22
_CMD_WRITE_RAM_BW           = 0x24
_CMD_WRITE_VCOM             = 0x2C
_CMD_WRITE_LUT              = 0x32
_CMD_SET_RAM_X_ADDR         = 0x44
_CMD_SET_RAM_Y_ADDR         = 0x45
_CMD_SET_RAM_X_COUNTER      = 0x4E
_CMD_SET_RAM_Y_COUNTER      = 0x4F
_CMD_BORDER_WAVEFORM_CTRL   = 0x3C
_CMD_DEEP_SLEEP             = 0x10


class EPaperDisplay:
    """
    Drive a monochrome Waveshare e-paper display from an ESP32.

    Parameters
    ----------
    display_type : str
        One of the keys in DISPLAY_SPECS.
    rotation : int
        Clockwise rotation in degrees (0, 90, 180, or 270).
    **pin_overrides
        Override any of the default GPIO numbers:
        sck, mosi, cs, dc, rst, busy.
    """

    def __init__(self, display_type="epd2in13v2", rotation=0, **pin_overrides):
        if display_type not in DISPLAY_SPECS:
            raise ValueError(
                f"Unsupported display type: {display_type}. "
                f"Choose from {list(DISPLAY_SPECS)}"
            )

        spec = DISPLAY_SPECS[display_type]
        self.width = spec["width"]
        self.height = spec["height"]
        self.rotation = rotation % 360

        pins = {**_DEFAULT_PINS, **pin_overrides}
        self._cs   = Pin(pins["cs"],   Pin.OUT, value=1)
        self._dc   = Pin(pins["dc"],   Pin.OUT, value=0)
        self._rst  = Pin(pins["rst"],  Pin.OUT, value=1)
        self._busy = Pin(pins["busy"], Pin.IN)
        self._spi  = SPI(
            1,
            baudrate=4_000_000,
            polarity=0,
            phase=0,
            sck=Pin(pins["sck"]),
            mosi=Pin(pins["mosi"]),
        )

        self._initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def init(self):
        """Hardware reset and display initialisation sequence."""
        self._reset()
        self._wait_busy()

        self._send_cmd(_CMD_SW_RESET)
        self._wait_busy()

        # Driver output – set gate lines from spec
        gate_lines = self.height - 1
        self._send_cmd(_CMD_DRIVER_OUTPUT_CTRL)
        self._send_data(gate_lines & 0xFF)
        self._send_data((gate_lines >> 8) & 0x01)
        self._send_data(0x00)

        # Data entry mode: X increment, Y increment
        self._send_cmd(_CMD_DATA_ENTRY_MODE)
        self._send_data(0x03)

        # Set RAM X address range
        self._send_cmd(_CMD_SET_RAM_X_ADDR)
        self._send_data(0x00)
        self._send_data((self.width // 8) - 1)

        # Set RAM Y address range
        self._send_cmd(_CMD_SET_RAM_Y_ADDR)
        self._send_data(0x00)
        self._send_data(0x00)
        self._send_data(gate_lines & 0xFF)
        self._send_data((gate_lines >> 8) & 0x01)

        # Border waveform – keep border white
        self._send_cmd(_CMD_BORDER_WAVEFORM_CTRL)
        self._send_data(0x05)

        # Use internal temperature sensor
        self._send_cmd(_CMD_TEMP_SENSOR_CTRL)
        self._send_data(0x80)

        # Reset RAM address counters
        self._send_cmd(_CMD_SET_RAM_X_COUNTER)
        self._send_data(0x00)
        self._send_cmd(_CMD_SET_RAM_Y_COUNTER)
        self._send_data(0x00)
        self._send_data(0x00)

        self._wait_busy()
        self._initialized = True

    def display(self, buf):
        """
        Push a raw monochrome frame buffer to the display and refresh.

        Parameters
        ----------
        buf : bytes | bytearray
            Raw 1-bit-per-pixel data, row-major, MSB first.
            Required length: ceil(width / 8) * height bytes.
            A *set* bit (1) means WHITE; a *cleared* bit (0) means BLACK.
        """
        if not self._initialized:
            self.init()

        expected = ((self.width + 7) // 8) * self.height
        if len(buf) != expected:
            raise ValueError(
                f"Buffer size mismatch: got {len(buf)}, expected {expected}"
            )

        # Reset RAM address counters before writing
        self._send_cmd(_CMD_SET_RAM_X_COUNTER)
        self._send_data(0x00)
        self._send_cmd(_CMD_SET_RAM_Y_COUNTER)
        self._send_data(0x00)
        self._send_data(0x00)

        self._send_cmd(_CMD_WRITE_RAM_BW)
        for byte in buf:
            self._send_data(byte)

        self._send_cmd(_CMD_DISPLAY_UPDATE_CTRL2)
        self._send_data(0xF7)
        self._send_cmd(_CMD_MASTER_ACTIVATION)
        self._wait_busy()

    def clear(self, white=True):
        """Fill the display with white (default) or black."""
        fill_byte = 0xFF if white else 0x00
        buf_size = ((self.width + 7) // 8) * self.height
        self.display(bytes([fill_byte] * buf_size))

    def sleep(self):
        """Put the display controller into deep-sleep mode (saves power)."""
        self._send_cmd(_CMD_DEEP_SLEEP)
        self._send_data(0x01)
        self._initialized = False

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _reset(self):
        self._rst(1)
        time.sleep_ms(10)
        self._rst(0)
        time.sleep_ms(10)
        self._rst(1)
        time.sleep_ms(10)

    def _wait_busy(self, timeout_ms=5000):
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while self._busy.value() == 1:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                raise OSError("E-paper display busy timeout")
            time.sleep_ms(10)

    def _send_cmd(self, cmd):
        self._dc(0)
        self._cs(0)
        self._spi.write(bytes([cmd]))
        self._cs(1)

    def _send_data(self, data):
        self._dc(1)
        self._cs(0)
        self._spi.write(bytes([data]))
        self._cs(1)
