"""Measure microphone levels using the same input configuration as the bot.

Keep quiet briefly, then speak normally. Compare the RMS readings with
ENERGY_THRESHOLD in voice_engine.py. Press Ctrl+C to stop.
"""

import audioop
import time

import speech_recognition as sr

from mic_config import ENERGY_THRESHOLD, MIC_DEVICE_INDEX


CHUNK = 2048
device_label = "Windows default" if MIC_DEVICE_INDEX is None else str(MIC_DEVICE_INDEX)

try:
    with sr.Microphone(device_index=MIC_DEVICE_INDEX, chunk_size=CHUNK) as mic:
        print(f"Monitoring device [{device_label}] @ {mic.SAMPLE_RATE} Hz, mono")
        print(f"Current energy threshold: {ENERGY_THRESHOLD}")
        print("Keep quiet, then speak normally. Press Ctrl+C to stop.")
        print("-" * 60)
        while True:
            data = mic.stream.read(CHUNK)
            rms = audioop.rms(data, mic.SAMPLE_WIDTH)
            bar = "#" * min(50, rms // 200)
            print(f"RMS: {rms:6d} |{bar:<50}|", flush=True)
            time.sleep(0.1)
except KeyboardInterrupt:
    pass
except Exception as exc:
    print(f"Could not read microphone: {type(exc).__name__}: {exc}")
finally:
    print("\nDone. Compare quiet and speech RMS with ENERGY_THRESHOLD in voice_engine.py.")
