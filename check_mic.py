"""
check_mic.py - Microphone Diagnostic & Hardware Volume Meter
Run this tool to test if your microphone is receiving sound and speech.

Usage:
    python check_mic.py
"""

import sys
import time
import audioop
import json
import pyaudio
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)

print("=" * 60)
print("      SIT ROBOT MICROPHONE & AUDIO HARDWARE CHECK")
print("=" * 60)

pa = pyaudio.PyAudio()
default_device = pa.get_default_input_device_info()
device_index = int(default_device["index"])
sample_rate = int(default_device.get("defaultSampleRate", 16000))
print(f"Default Microphone : {default_device.get('name')}")
print(f"Sample Rate        : {sample_rate} Hz")
print(f"Input Channels     : {default_device.get('maxInputChannels')}")
print("-" * 60)

try:
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=sample_rate,
                     input=True, input_device_index=device_index, frames_per_buffer=2000)
except Exception as e:
    print(f"Error opening microphone: {e}")
    sys.exit(1)

m = Model("models/vosk-model-small-en-us-0.15")
rec = KaldiRecognizer(m, sample_rate)

print("\n[INSTRUCTIONS] Speak into your microphone now for 6 seconds...")
print("The bar below shows live volume level and detected speech:")
print("-" * 60)

start = time.time()
while time.time() - start < 6.0:
    try:
        data = stream.read(2000, exception_on_overflow=False)
    except Exception:
        continue

    rms = audioop.rms(data, 2)
    bars = min(30, int(rms / 150))
    meter = "#" * bars + "-" * (30 - bars)

    detected = ""
    if rec.AcceptWaveform(data):
        res = json.loads(rec.Result()).get("text", "")
        if res:
            detected = f" >> SPEECH: '{res}'"
    else:
        part = json.loads(rec.PartialResult()).get("partial", "")
        if part:
            detected = f" >> HEARING: '{part}'"

    print(f"\rLevel: [{meter}] (RMS: {rms:5d}){detected}", end="", flush=True)

final_res = json.loads(rec.FinalResult()).get("text", "")
print("\n" + "-" * 60)
if final_res:
    print(f"Final Captured Speech: '{final_res}'")
else:
    print("No final speech buffer detected.")

stream.stop_stream()
stream.close()
pa.terminate()

print("=" * 60)
print("Microphone diagnostic completed.")
