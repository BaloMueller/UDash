import logging
import os
import platform
import socket

from flask import Blueprint, current_app, jsonify, render_template

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

system_info_bp = Blueprint("system_info", __name__)


def _get_cpu_freq():
    """Return CPU frequency as a formatted string (e.g. '2.5 GHz').

    Priority: psutil current -> psutil max -> /proc/cpuinfo cpu MHz ->
    sysfs scaling_cur_freq -> sysfs cpuinfo_max_freq -> None.
    """
    # 1. psutil (preferred – works on ARM and x86)
    if psutil is not None:
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                mhz = freq.current if freq.current and freq.current > 0 else freq.max
                if mhz and mhz > 0:
                    return f"{round(mhz / 1000, 1)} GHz"
        except Exception:
            pass

    # 2. /proc/cpuinfo "cpu MHz" line
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    mhz = float(line.split(":")[1].strip())
                    if mhz > 0:
                        return f"{round(mhz / 1000, 1)} GHz"
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    # 3. sysfs frequency files (kHz)
    freq_paths = [
        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq",
        "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq",
    ]
    for path in freq_paths:
        try:
            with open(path) as f:
                freq_khz = int(f.read().strip())
                if freq_khz > 0:
                    return f"{round(freq_khz / 1_000_000, 1)} GHz"
        except (FileNotFoundError, PermissionError, ValueError):
            continue

    return None


def _get_cpu_info():
    """Return CPU model name, frequency string, and core count."""
    model = platform.processor() or "Unknown"
    cores = None

    try:
        with open("/proc/cpuinfo") as f:
            core_count = 0
            for line in f:
                if line.startswith("model name"):
                    model = line.split(":")[1].strip()
                if line.startswith("processor"):
                    core_count += 1
            if core_count > 0:
                cores = core_count
    except (FileNotFoundError, PermissionError):
        pass

    freq = _get_cpu_freq()
    return {"model": model, "freq": freq, "cores": cores}


def _is_wsl():
    """Detect if running inside Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _get_host_physical_memory():
    """Try to get actual physical RAM from Windows host (WSL2 only).

    Uses PowerShell interop to query the host's total physical memory.
    Returns the value in bytes or None if unavailable.
    """
    import subprocess

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _get_memory_info():
    """Return total and used RAM in human-readable format.

    On WSL, attempts to report the host's physical RAM via PowerShell.
    Falls back to /proc/meminfo MemTotal with an annotation when the
    true installed amount cannot be determined.
    """
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

        allocated = _format_bytes(total_kb * 1024)
        used = _format_bytes(used_kb * 1024)

        if _is_wsl():
            host_mem = _get_host_physical_memory()
            if host_mem:
                return {
                    "total": _format_bytes(host_mem),
                    "used": used,
                    "note": f"WSL allocated: {allocated}",
                }
            return {
                "total": allocated,
                "used": used,
                "note": "WSL allocated",
            }

        return {"total": allocated, "used": used, "note": None}
    except (FileNotFoundError, PermissionError):
        return {"total": "N/A", "used": "N/A", "note": None}


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
    """Return OS name, version, distribution ID, and pretty name."""
    name = "Unknown"
    version = None
    distro_id = None
    pretty_name = None

    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    pretty_name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION="):
                    version = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("NAME=") and not line.startswith("NAME=\"\n"):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("ID="):
                    distro_id = line.split("=", 1)[1].strip().strip('"')
    except (FileNotFoundError, PermissionError):
        name = f"{platform.system()} {platform.release()}"

    return {
        "name": name,
        "version": version,
        "distro": distro_id,
        "pretty_name": pretty_name or name,
    }


def _get_architecture():
    """Return the system architecture (e.g. x86_64, aarch64)."""
    return platform.machine() or "Unknown"


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
    """Return display information reusing InkyPi's configured display type.

    Uses the same ``display_type`` config key that ``DisplayManager.__init__``
    reads to select the concrete display driver, and ``get_resolution()`` for
    the configured panel size.
    """
    device_config = display_manager.device_config
    display_type = device_config.get_config("display_type", default="unknown")

    # Friendly name – mirrors DisplayManager dispatch logic
    if display_type == "mock":
        name = "Mock (Development)"
    elif display_type == "inky":
        name = "Inky (Pimoroni)"
    elif display_type.startswith("epd"):
        name = display_type  # Waveshare model id, e.g. "epd7in3e"
    else:
        name = display_type

    # Resolution from the same config source used by display rendering
    resolution = None
    try:
        w, h = device_config.get_resolution()
        resolution = f"{w} × {h}"
    except (TypeError, ValueError, KeyError):
        pass

    return {"name": name, "type": display_type, "resolution": resolution}


def _get_kernel_info():
    """Return kernel version string."""
    return platform.release()


def _get_device_name(device_config):
    """Return the configured device name from InkyPi config."""
    return device_config.get_config("name", default="InkyPi")


def _format_bytes(num_bytes):
    """Format bytes into a human-readable string (e.g. 3.7 GB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def _ram_secondary(mem):
    """Build secondary text for the RAM card, annotating WSL when applicable."""
    usage = f"{mem['used']} of {mem['total']} used"
    note = mem.get("note")
    if note:
        return f"{usage} ({note})"
    return usage


def _collect_system_info(display_manager):
    """Collect all system information split into highlight cards and specification sections."""
    cpu = _get_cpu_info()
    mem = _get_memory_info()
    storage = _get_storage_info()
    os_info = _get_os_info()
    display = _get_display_info(display_manager)
    local_ip = _get_local_ip()
    device_config = display_manager.device_config

    cards = [
        {
            "icon": "storage",
            "label": "Storage",
            "value": storage["total"],
            "secondary": f"{storage['used']} of {storage['total']} used",
        },
        {
            "icon": "memory",
            "label": "Installed RAM",
            "value": mem["total"],
            "secondary": _ram_secondary(mem),
        },
        {
            "icon": "cpu",
            "label": "CPU",
            "value": cpu["model"],
            "secondary": cpu["freq"],
        },
        {
            "icon": "os",
            "label": "OS",
            "value": os_info["pretty_name"],
            "secondary": os_info["version"],
        },
        {
            "icon": "display",
            "label": "Display",
            "value": display["name"],
            "secondary": display["resolution"],
        },
        {
            "icon": "network",
            "label": "Local IP",
            "value": local_ip,
        },
    ]

    ram_spec = mem["total"]
    if mem.get("note"):
        ram_spec += f" ({mem['note']})"

    device_specs = [
        {"label": "Device name", "value": _get_device_name(device_config)},
        {"label": "Hostname", "value": _get_hostname()},
        {"label": "Model", "value": _get_device_model()},
        {"label": "Architecture", "value": _get_architecture()},
        {"label": "CPU", "value": cpu["model"]},
        {"label": "CPU cores", "value": str(cpu["cores"]) if cpu["cores"] else "N/A"},
        {"label": "CPU frequency", "value": cpu["freq"] or "N/A"},
        {"label": "RAM", "value": ram_spec},
        {"label": "Display type", "value": display["type"]},
        {"label": "Display resolution", "value": display["resolution"] or "N/A"},
    ]

    system_specs = [
        {"label": "OS name", "value": os_info["name"]},
        {"label": "OS version", "value": os_info["version"] or "N/A"},
        {"label": "Distribution", "value": os_info["distro"] or "N/A"},
        {"label": "Kernel", "value": _get_kernel_info()},
        {"label": "Pretty name", "value": os_info["pretty_name"]},
    ]

    return cards, device_specs, system_specs


@system_info_bp.route("/system-info")
def system_info_page():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    cards, device_specs, system_specs = _collect_system_info(display_manager)
    return render_template(
        "system_info.html",
        hostname=hostname,
        cards=cards,
        device_specs=device_specs,
        system_specs=system_specs,
    )


@system_info_bp.route("/api/system-info")
def system_info_api():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    cards, device_specs, system_specs = _collect_system_info(display_manager)
    return jsonify({
        "hostname": hostname,
        "cards": cards,
        "device_specs": device_specs,
        "system_specs": system_specs,
    })
