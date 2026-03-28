import logging
import os
import platform
import socket

from flask import Blueprint, current_app, jsonify, render_template

logger = logging.getLogger(__name__)

system_info_bp = Blueprint("system_info", __name__)


def _get_cpu_info():
    """Return CPU model name and frequency."""
    model = platform.processor() or "Unknown"
    freq_ghz = None

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    model = line.split(":")[1].strip()
                    break
    except (FileNotFoundError, PermissionError):
        pass

    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq") as f:
            freq_khz = int(f.read().strip())
            freq_ghz = round(freq_khz / 1_000_000, 2)
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    return {"model": model, "freq_ghz": freq_ghz}


def _get_memory_info():
    """Return total and used RAM in human-readable format."""
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]  # value in kB
                    meminfo[key] = int(val)

        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", 0)
        used_kb = total_kb - available_kb
        return {
            "total": _format_bytes(total_kb * 1024),
            "used": _format_bytes(used_kb * 1024),
        }
    except (FileNotFoundError, PermissionError):
        return {"total": "N/A", "used": "N/A"}


def _get_storage_info():
    """Return total and used disk space for the root filesystem."""
    try:
        stat = os.statvfs("/")
        total = stat.f_frsize * stat.f_blocks
        used = stat.f_frsize * (stat.f_blocks - stat.f_bfree)
        return {
            "total": _format_bytes(total),
            "used": _format_bytes(used),
        }
    except OSError:
        return {"total": "N/A", "used": "N/A"}


def _get_os_info():
    """Return OS name and version."""
    name = "Unknown"
    version = None

    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION="):
                    version = line.split("=", 1)[1].strip().strip('"')
    except (FileNotFoundError, PermissionError):
        name = f"{platform.system()} {platform.release()}"

    return {"name": name, "version": version}


def _get_device_model():
    """Return the device model (e.g. Raspberry Pi 4 Model B)."""
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip().rstrip("\x00")
    except (FileNotFoundError, PermissionError):
        return platform.machine() or "Unknown"


def _get_uptime():
    """Return system uptime as a human-readable string."""
    try:
        with open("/proc/uptime") as f:
            seconds = int(float(f.read().split()[0]))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except (FileNotFoundError, PermissionError):
        return "N/A"


def _get_last_boot():
    """Return last boot time as a formatted string."""
    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
        import time
        boot_timestamp = time.time() - uptime_seconds
        from datetime import datetime
        boot_dt = datetime.fromtimestamp(boot_timestamp)
        return boot_dt.strftime("%Y-%m-%d %H:%M")
    except (FileNotFoundError, PermissionError):
        return "N/A"


def _get_local_ip():
    """Return the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except (OSError, socket.error):
        return "N/A"


def _get_hostname():
    """Return the system hostname."""
    return socket.gethostname()


def _get_display_info(display_manager):
    """Return display name and model from the display manager."""
    display_type = display_manager.device_config.get_config("display_type", default="unknown")
    display_obj = getattr(display_manager, "display", None)
    display_class = type(display_obj).__name__ if display_obj else display_type

    model = None
    if display_type not in ("mock", "inky"):
        model = display_type

    return {"name": display_class, "model": model}


def _format_bytes(num_bytes):
    """Format bytes into a human-readable string (e.g. 3.7 GB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def _collect_system_info(display_manager):
    """Collect all system information cards."""
    cpu = _get_cpu_info()
    mem = _get_memory_info()
    storage = _get_storage_info()
    os_info = _get_os_info()
    display = _get_display_info(display_manager)

    cards = [
        {
            "icon": "cpu",
            "label": "CPU",
            "value": cpu["model"],
            "secondary": f"{cpu['freq_ghz']} GHz" if cpu["freq_ghz"] else None,
        },
        {
            "icon": "memory",
            "label": "RAM",
            "value": mem["total"],
            "secondary": f"{mem['used']} / {mem['total']} used",
        },
        {
            "icon": "storage",
            "label": "Storage",
            "value": storage["total"],
            "secondary": f"{storage['used']} / {storage['total']} used",
        },
        {
            "icon": "os",
            "label": "OS",
            "value": os_info["name"],
            "secondary": os_info["version"],
        },
        {
            "icon": "device",
            "label": "Device",
            "value": _get_device_model(),
        },
        {
            "icon": "display",
            "label": "Display",
            "value": display["name"],
            "secondary": display["model"],
        },
        {
            "icon": "uptime",
            "label": "Uptime",
            "value": _get_uptime(),
        },
        {
            "icon": "boot",
            "label": "Last Boot",
            "value": _get_last_boot(),
        },
        {
            "icon": "network",
            "label": "Local IP",
            "value": _get_local_ip(),
        },
    ]
    return cards


@system_info_bp.route("/system-info")
def system_info_page():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    cards = _collect_system_info(display_manager)
    return render_template("system_info.html", hostname=hostname, cards=cards)


@system_info_bp.route("/api/system-info")
def system_info_api():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    cards = _collect_system_info(display_manager)
    return jsonify({"hostname": hostname, "cards": cards})
