"""Shared microphone configuration for the runtime and diagnostics."""

import os


_device_override = os.environ.get("HUMANOID_MIC_DEVICE", "").strip()
try:
    MIC_DEVICE_INDEX = int(_device_override) if _device_override else None
except ValueError as exc:
    raise ValueError("HUMANOID_MIC_DEVICE must be a non-negative PortAudio device index") from exc

if MIC_DEVICE_INDEX is not None and MIC_DEVICE_INDEX < 0:
    raise ValueError("HUMANOID_MIC_DEVICE must be a non-negative PortAudio device index")

MIC_TARGET_RATE = 16000
ENERGY_THRESHOLD = 300
