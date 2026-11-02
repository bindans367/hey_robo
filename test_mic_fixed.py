"""
test_mic_fixed.py - Quick mic pipeline test with full debug output.
Run this, speak when prompted, and read ALL lines of output.
"""
import sys
sys.path.insert(0, r"c:\Users\Admin\Desktop\Humanoid")

from voice_engine import listen, speak, MIC_DEVICE_INDEX, ENERGY_THRESHOLD

print("=" * 60)
print(f"  SIT Robot -- Mic Pipeline Test")
print(f"  Device Index : {MIC_DEVICE_INDEX!r}  (None = current Windows default)")
print("  Native Rate  : detected from selected device")
print(f"  Energy Thresh: {ENERGY_THRESHOLD}")
print("=" * 60)
print()
print("  Starting in 2 seconds - GET READY TO SPEAK...")
import time; time.sleep(2)

import winsound
winsound.Beep(1000, 400)
print("\n  >>> SPEAK NOW (you have 8 seconds) <<<\n")

text = listen(timeout=8, phrase_time_limit=8)

print()
print("=" * 60)
if text:
    print(f"  SUCCESS : '{text}'")
    speak(f"I heard: {text}")
else:
    print("  FAILED  : listen() returned empty string")
    print("  Check the [MIC] lines above for TIMEOUT vs RMS=0")
print("=" * 60)
