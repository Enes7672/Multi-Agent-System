"""
Hardware Detection Module
Detects CPU, RAM, GPU information and makes intelligent decisions.
"""

import psutil
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class HardwareInfo:
    cpu_cores: int
    cpu_usage: float
    ram_total_gb: float
    ram_available_gb: float
    ram_usage_percent: float
    gpu_available: bool
    gpu_name: Optional[str]
    gpu_memory_mb: Optional[float]
    gpu_usage_percent: Optional[float]
    platform: str
    is_low_end: bool
    recommended_model: str
    max_concurrent_agents: int


class HardwareDetector:
    LOW_RAM_THRESHOLD_GB = 8
    LOW_CPU_THRESHOLD = 4

    MODEL_SIZES = {
        "codellama:7b": 3.8,
        "codellama:13b": 7.4,
        "deepseek-coder:6.7b": 3.9,
        "deepseek-coder:33b": 18.3,
        "starcoder:3b": 1.5,
        "starcoder:7b": 4.0,
        "starcoder:15b": 8.9,
        "phi-2": 1.4,
        "mistral:7b": 4.1,
    }

    def __init__(self):
        self._info: Optional[HardwareInfo] = None

    def detect(self) -> HardwareInfo:
        if self._info is not None:
            return self._info

        cpu_cores = psutil.cpu_count(logical=True)
        cpu_usage = psutil.cpu_percent(interval=1)

        ram = psutil.virtual_memory()
        ram_total_gb = ram.total / (1024 ** 3)
        ram_available_gb = ram.available / (1024 ** 3)
        ram_usage_percent = ram.percent

        gpu_info = self._detect_gpu()

        is_low_end = (
            ram_total_gb < self.LOW_RAM_THRESHOLD_GB or
            cpu_cores < self.LOW_CPU_THRESHOLD
        )

        recommended = self._recommend_model(ram_available_gb, is_low_end)
        max_agents = self._calculate_max_agents(ram_available_gb, is_low_end)

        self._info = HardwareInfo(
            cpu_cores=cpu_cores,
            cpu_usage=cpu_usage,
            ram_total_gb=ram_total_gb,
            ram_available_gb=ram_available_gb,
            ram_usage_percent=ram_usage_percent,
            gpu_available=gpu_info["available"],
            gpu_name=gpu_info.get("name"),
            gpu_memory_mb=gpu_info.get("memory_mb"),
            gpu_usage_percent=gpu_info.get("usage_percent"),
            platform=platform.system(),
            is_low_end=is_low_end,
            recommended_model=recommended,
            max_concurrent_agents=max_agents
        )

        logger.info(f"Hardware detected: {self._info}")
        return self._info

    def _detect_gpu(self) -> Dict[str, Any]:
        result = {"available": False}

        try:
            if platform.system() == "Windows":
                try:
                    output = subprocess.check_output(
                        ["nvidia-smi", "--query-gpu=name,memory.total,utilization.gpu",
                         "--format=csv,noheader,nounits"],
                        text=True, timeout=5
                    )
                    if output.strip():
                        parts = output.strip().split(", ")
                        result["available"] = True
                        result["name"] = parts[0]
                        result["memory_mb"] = float(parts[1])
                        result["usage_percent"] = float(parts[2])
                        result["vendor"] = "NVIDIA"
                        return result
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

            elif platform.system() == "Linux":
                try:
                    output = subprocess.check_output(["lspci", "-v"], text=True, timeout=5)
                    if "NVIDIA" in output:
                        result["available"] = True
                        result["vendor"] = "NVIDIA"
                        for line in output.split("\n"):
                            if "NVIDIA" in line and "VGA" in line:
                                result["name"] = line.split(":")[-1].strip()
                                break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

            elif platform.system() == "Darwin":
                try:
                    output = subprocess.check_output(
                        ["sysctl", "-n", "machdep.cpu.brand_string"],
                        text=True, timeout=5
                    )
                    if "Apple" in output:
                        result["available"] = True
                        result["name"] = output.strip()
                        result["vendor"] = "Apple"
                        result["is_apple_silicon"] = True
                        mem_output = subprocess.check_output(
                            ["sysctl", "-n", "hw.memsize"],
                            text=True, timeout=5
                        )
                        mem_bytes = int(mem_output.strip())
                        result["memory_mb"] = mem_bytes / (1024 * 1024)
                        return result
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

        except Exception as e:
            logger.warning(f"GPU detection error: {e}")

        return result

    def _recommend_model(self, available_ram_gb: float, is_low_end: bool) -> str:
        if is_low_end:
            return "starcoder:3b" if available_ram_gb >= 4 else "phi-2"

        if available_ram_gb >= 20:
            return "codellama:13b"
        elif available_ram_gb >= 8:
            return "codellama:7b"
        elif available_ram_gb >= 5:
            return "deepseek-coder:6.7b"
        elif available_ram_gb >= 2:
            return "starcoder:3b"
        else:
            return "phi-2"

    def _calculate_max_agents(self, available_ram_gb: float, is_low_end: bool) -> int:
        if is_low_end:
            return 1

        max_by_ram = int(available_ram_gb / 2)
        cpu_cores = psutil.cpu_count(logical=True)
        max_by_cpu = max(1, cpu_cores // 2)

        return min(max_by_ram, max_by_cpu, 3)

    def get_status_report(self) -> str:
        info = self.detect()

        report = f"""
=== HARDWARE STATUS ===
Platform: {info.platform}
CPU Cores: {info.cpu_cores} ({info.cpu_usage}% usage)
RAM: {info.ram_total_gb:.1f} GB total, {info.ram_available_gb:.1f} GB available ({info.ram_usage_percent}% usage)
GPU: {'Available' if info.gpu_available else 'Not found'}
"""
        if info.gpu_available:
            report += f"GPU Name: {info.gpu_name}\n"
            report += f"GPU Memory: {info.gpu_memory_mb:.0f} MB\n"
            report += f"GPU Usage: {info.gpu_usage_percent}%\n"

        report += f"""
=== RECOMMENDATIONS ===
Hardware Level: {'Low-end' if info.is_low_end else 'High-end'}
Recommended Model: {info.recommended_model}
Max Concurrent Agents: {info.max_concurrent_agents}
"""
        return report

    def can_run_model(self, model_name: str) -> bool:
        info = self.detect()
        model_size = self.MODEL_SIZES.get(model_name)
        if model_size is None:
            logger.warning(f"Unknown model: {model_name}")
            return False

        required_ram = model_size * 1.2
        return info.ram_available_gb >= required_ram

    def refresh(self) -> HardwareInfo:
        self._info = None
        return self.detect()


_detector: Optional[HardwareDetector] = None


def get_detector() -> HardwareDetector:
    global _detector
    if _detector is None:
        _detector = HardwareDetector()
    return _detector
