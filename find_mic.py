"""
find_mic.py - Quick diagnostic to find input devices that return audio.
"""
import speech_recognition as sr
import pyaudio, audioop

pa = pyaudio.PyAudio()
print("Scanning all microphone devices for active audio signal...\n")

best_idx = None
best_rms = -1

for i, name in enumerate(sr.Microphone.list_microphone_names()):
    info = pa.get_device_info_by_index(i)
    max_in = info.get("maxInputChannels", 0)
    if max_in <= 0:
        continue
    
    rate = int(info.get("defaultSampleRate", 44100))
    # Match the mono capture used by SpeechRecognition in voice_engine.py.
    ch = 1
    
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=ch, rate=rate,
                         input=True, input_device_index=i, frames_per_buffer=1024)
        rms_vals = []
        for _ in range(5):
            data = stream.read(1024, exception_on_overflow=False)
            rms_vals.append(audioop.rms(data, 2))
        stream.stop_stream()
        stream.close()
        avg_rms = sum(rms_vals) / len(rms_vals)
        
        marker = " <-- ACTIVE" if avg_rms > 100 else ""
        print(f"[{i:2d}] {name[:55]:55} | RMS: {avg_rms:7.1f}{marker}")
        
        if avg_rms > best_rms:
            best_rms = avg_rms
            best_idx = i
    except Exception:
        pass

pa.terminate()
if best_idx is not None:
    print(f"\n>>> Best readable input: Device [{best_idx}] (RMS: {best_rms:.1f})")
    print(f">>> Run bot with: python bot.py --mic {best_idx}")
else:
    print("\n>>> No readable input found. Check Windows microphone permissions and input selection.")
