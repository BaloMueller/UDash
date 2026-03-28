import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from blueprints.system_info import (
    _format_bytes,
    _get_cpu_info,
    _get_cpu_freq,
    _get_memory_info,
    _get_storage_info,
    _get_os_info,
    _get_device_model,
    _get_uptime,
    _get_last_boot,
    _get_local_ip,
    _get_hostname,
    _get_display_info,
    _get_kernel_info,
    _get_device_name,
    _get_architecture,
    _is_wsl,
    _get_host_physical_memory,
    _ram_secondary,
    _collect_system_info,
)


class TestFormatBytes:
    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert _format_bytes(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert _format_bytes(1024 ** 4) == "1.0 TB"


class TestGetCpuFreq:
    @patch("blueprints.system_info.psutil")
    def test_psutil_current(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = MagicMock(current=2500.0, max=3000.0)
        assert _get_cpu_freq() == "2.5 GHz"

    @patch("blueprints.system_info.psutil")
    def test_psutil_max_fallback(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = MagicMock(current=0.0, max=1800.0)
        assert _get_cpu_freq() == "1.8 GHz"

    @patch("blueprints.system_info.psutil")
    def test_psutil_none_falls_through(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = None
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert _get_cpu_freq() is None

    @patch("blueprints.system_info.psutil", new=None)
    def test_no_psutil_reads_proc_cpuinfo(self):
        cpuinfo = "cpu MHz\t: 1000.000\n"
        with patch("builtins.open", MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=iter(cpuinfo.splitlines(True))),
                __exit__=MagicMock(return_value=False),
            )
        )):
            assert _get_cpu_freq() == "1.0 GHz"


class TestGetCpuInfo:
    @patch("blueprints.system_info._get_cpu_freq", return_value=None)
    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("platform.processor", return_value="x86_64")
    def test_fallback_to_platform(self, mock_proc, mock_open, mock_freq):
        result = _get_cpu_info()
        assert result["model"] == "x86_64"
        assert result["freq"] is None
        assert result["cores"] is None

    @patch("blueprints.system_info._get_cpu_freq", return_value="2.5 GHz")
    @patch("builtins.open")
    def test_reads_proc_cpuinfo(self, mock_open, mock_freq):
        cpuinfo_content = "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i5-12400\nprocessor\t: 1\nmodel name\t: Intel(R) Core(TM) i5-12400\n"
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=iter(cpuinfo_content.splitlines(True))),
            __exit__=MagicMock(return_value=False),
        )
        result = _get_cpu_info()
        assert "i5-12400" in result["model"]
        assert result["cores"] == 2
        assert result["freq"] == "2.5 GHz"


class TestIsWsl:
    @patch("builtins.open")
    def test_detects_wsl(self, mock_open):
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(
                return_value="Linux version 5.15.0 (Microsoft)"
            ))),
            __exit__=MagicMock(return_value=False),
        )
        assert _is_wsl() is True

    @patch("builtins.open")
    def test_non_wsl(self, mock_open):
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(
                return_value="Linux version 6.1.0-rpi7"
            ))),
            __exit__=MagicMock(return_value=False),
        )
        assert _is_wsl() is False

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _is_wsl() is False


class TestGetHostPhysicalMemory:
    @patch("subprocess.run")
    def test_returns_bytes(self, mock_run):
        import subprocess
        mock_run.return_value = MagicMock(returncode=0, stdout="34359738368\n")
        result = _get_host_physical_memory()
        assert result == 34359738368

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_none_on_failure(self, mock_run):
        assert _get_host_physical_memory() is None


class TestRamSecondary:
    def test_normal(self):
        mem = {"total": "4.0 GB", "used": "2.0 GB", "note": None}
        assert _ram_secondary(mem) == "2.0 GB of 4.0 GB used"

    def test_wsl_with_host_ram(self):
        mem = {"total": "32.0 GB", "used": "8.0 GB", "note": "WSL allocated: 15.5 GB"}
        assert _ram_secondary(mem) == "8.0 GB of 32.0 GB used (WSL allocated: 15.5 GB)"

    def test_wsl_no_host_ram(self):
        mem = {"total": "15.5 GB", "used": "8.0 GB", "note": "WSL allocated"}
        assert _ram_secondary(mem) == "8.0 GB of 15.5 GB used (WSL allocated)"


class TestGetMemoryInfo:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing_proc(self, mock_open):
        result = _get_memory_info()
        assert result["total"] == "N/A"
        assert result["used"] == "N/A"
        assert result["note"] is None


class TestGetStorageInfo:
    @patch("os.statvfs")
    def test_returns_storage(self, mock_statvfs):
        mock_statvfs.return_value = MagicMock(
            f_frsize=4096, f_blocks=2621440, f_bfree=1310720
        )
        result = _get_storage_info()
        assert "GB" in result["total"] or "MB" in result["total"]

    @patch("os.statvfs", side_effect=OSError)
    def test_fallback_on_error(self, mock_statvfs):
        result = _get_storage_info()
        assert result["total"] == "N/A"


class TestGetOsInfo:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_to_platform(self, mock_open):
        result = _get_os_info()
        assert result["name"] != "Unknown"
        assert result["pretty_name"] is not None
        assert result["distro"] is None


class TestGetDeviceModel:
    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("platform.machine", return_value="x86_64")
    def test_fallback_to_platform(self, mock_machine, mock_open):
        result = _get_device_model()
        assert result == "x86_64"


class TestGetUptime:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _get_uptime() == "N/A"

    @patch("builtins.open")
    def test_parses_uptime(self, mock_open):
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value="90061.23 180000.00"))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        result = _get_uptime()
        assert "1d" in result
        assert "h" in result


class TestGetLastBoot:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _get_last_boot() == "N/A"


class TestGetLocalIp:
    @patch("socket.socket")
    def test_returns_ip(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.getsockname.return_value = ("192.168.1.100", 0)
        assert _get_local_ip() == "192.168.1.100"

    @patch("socket.socket", side_effect=OSError)
    def test_fallback_on_error(self, mock_socket_cls):
        assert _get_local_ip() == "N/A"


class TestGetHostname:
    @patch("socket.gethostname", return_value="inkypi")
    def test_returns_hostname(self, mock_hostname):
        assert _get_hostname() == "inkypi"


class TestGetDisplayInfo:
    def test_mock_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.return_value = (800, 480)
        result = _get_display_info(mock_dm)
        assert result["name"] == "Mock (Development)"
        assert result["type"] == "mock"
        assert result["resolution"] == "800 × 480"

    def test_inky_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "inky"
        mock_dm.device_config.get_resolution.return_value = (400, 300)
        result = _get_display_info(mock_dm)
        assert result["name"] == "Inky (Pimoroni)"
        assert result["type"] == "inky"
        assert result["resolution"] == "400 × 300"

    def test_waveshare_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "epd7in3e"
        mock_dm.device_config.get_resolution.return_value = (800, 480)
        result = _get_display_info(mock_dm)
        assert result["name"] == "epd7in3e"
        assert result["type"] == "epd7in3e"
        assert result["resolution"] == "800 × 480"

    def test_resolution_unavailable(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.side_effect = KeyError
        result = _get_display_info(mock_dm)
        assert result["resolution"] is None


class TestGetKernelInfo:
    @patch("platform.release", return_value="6.1.0-rpi7-rpi-v8")
    def test_returns_kernel(self, mock_release):
        assert _get_kernel_info() == "6.1.0-rpi7-rpi-v8"


class TestGetArchitecture:
    @patch("platform.machine", return_value="aarch64")
    def test_returns_arch(self, mock_machine):
        assert _get_architecture() == "aarch64"

    @patch("platform.machine", return_value="")
    def test_fallback_on_empty(self, mock_machine):
        assert _get_architecture() == "Unknown"


class TestGetDeviceName:
    def test_returns_config_name(self):
        mock_config = MagicMock()
        mock_config.get_config.return_value = "My InkyPi"
        assert _get_device_name(mock_config) == "My InkyPi"

    def test_returns_default(self):
        mock_config = MagicMock()
        mock_config.get_config.return_value = "InkyPi"
        assert _get_device_name(mock_config) == "InkyPi"


class TestCollectSystemInfo:
    @patch("blueprints.system_info._get_local_ip", return_value="192.168.1.1")
    @patch("blueprints.system_info._get_last_boot", return_value="2025-01-01 10:00")
    @patch("blueprints.system_info._get_uptime", return_value="5d 3h 20m")
    @patch("blueprints.system_info._get_device_model", return_value="Raspberry Pi 4")
    @patch("blueprints.system_info._get_os_info", return_value={"name": "Debian GNU/Linux", "version": "11", "distro": "debian", "pretty_name": "Debian GNU/Linux 11 (bullseye)"})
    @patch("blueprints.system_info._get_storage_info", return_value={"total": "32.0 GB", "used": "10.0 GB"})
    @patch("blueprints.system_info._get_memory_info", return_value={"total": "4.0 GB", "used": "2.0 GB", "note": None})
    @patch("blueprints.system_info._get_cpu_info", return_value={"model": "ARM Cortex-A72", "freq": "1.5 GHz", "cores": 4})
    @patch("blueprints.system_info._get_kernel_info", return_value="6.1.0-rpi7")
    @patch("blueprints.system_info._get_hostname", return_value="inkypi")
    @patch("blueprints.system_info._get_device_name", return_value="My InkyPi")
    @patch("blueprints.system_info._get_architecture", return_value="aarch64")
    def test_returns_cards_and_specs(self, *mocks):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.return_value = (800, 480)

        cards, device_specs, system_specs = _collect_system_info(mock_dm)

        # Verify cards
        card_labels = [c["label"] for c in cards]
        assert "Storage" in card_labels
        assert "Installed RAM" in card_labels
        assert "CPU" in card_labels
        assert "OS" in card_labels
        assert "Display" in card_labels
        assert "Local IP" in card_labels
        assert len(cards) == 6

        # Verify device specs
        dev_labels = [s["label"] for s in device_specs]
        assert "Device name" in dev_labels
        assert "Hostname" in dev_labels
        assert "Model" in dev_labels
        assert "Architecture" in dev_labels
        assert "CPU" in dev_labels
        assert "CPU cores" in dev_labels
        assert "CPU frequency" in dev_labels
        assert "RAM" in dev_labels
        assert "Display type" in dev_labels
        assert "Display resolution" in dev_labels
        assert len(device_specs) == 10

        # Verify system specs
        sys_labels = [s["label"] for s in system_specs]
        assert "OS name" in sys_labels
        assert "OS version" in sys_labels
        assert "Distribution" in sys_labels
        assert "Kernel" in sys_labels
        assert "Pretty name" in sys_labels
        assert len(system_specs) == 5
