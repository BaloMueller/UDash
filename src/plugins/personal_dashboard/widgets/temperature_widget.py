import subprocess


class TemperatureWidget:
    """Loads device CPU temperature using Raspberry Pi-friendly fallbacks."""

    @staticmethod
    def get_data():
        """Return CPU temperature string using multiple fallback strategies."""
        # 1. psutil - works on most platforms when sensors are available.
        try:
            import psutil
            temps = psutil.sensors_temperatures()
            for sensor_name in ("cpu_thermal", "cpu-thermal", "coretemp", "k10temp"):
                if sensor_name in temps and temps[sensor_name]:
                    current = temps[sensor_name][0].current
                    if current and current > 0:
                        return f"{current:.0f} °C"
            for entries in temps.values():
                if entries and entries[0].current > 0:
                    return f"{entries[0].current:.0f} °C"
        except Exception:
            pass

        # 2. vcgencmd - Raspberry Pi firmware command.
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and "temp=" in result.stdout:
                temp_str = result.stdout.split("=")[1].split("'")[0]
                return f"{float(temp_str):.0f} °C"
        except Exception:
            pass

        # 3. sysfs thermal zone - Linux fallback.
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                millideg = int(f.read().strip())
                if millideg > 0:
                    return f"{millideg / 1000:.0f} °C"
        except Exception:
            pass

        return None
