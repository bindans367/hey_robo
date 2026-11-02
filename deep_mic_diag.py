"""
deep_mic_diag.py - Complete mic diagnostic.
Run this and paste the full output so we can see exactly what's happening.
"""
import sys, audioop, io, wave, time
import pyaudio
import speech_recognition as sr

print("=" * 65)
print("  SIT Robot - Deep Microphone Diagnostic")
print("=" * 65)

pa = pyaudio.PyAudio()

# ── 1. List all devices ────────────────────────────────────────────
print("\n[1] All audio INPUT devices:")
print(f"    {'Idx':<5} {'Max-In':<8} {'Default-Rate':<14} {'Name'}")
print("    " + "-" * 58)
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        print(f"    [{i}]   ch={info['maxInputChannels']}   "
              f"{int(info['defaultSampleRate'])} Hz    "
              f"{info['name']}")

# ── 2. Identify default input ──────────────────────────────────────
try:
    defidx = pa.get_default_input_device_info()["index"]
    defname = pa.get_default_input_device_info()["name"]
    print(f"\n[2] Default input device: [{defidx}] {defname}")
except Exception as e:
    print(f"\n[2] Could not get default input: {e}")

# ── 3. RMS snapshot for every input device ─────────────────────────
print("\n[3] RMS power snapshot for each input device (0.5s read):")
print("    Keep QUIET during this test.\n")

CHUNK = 2048
rms_results = {}
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] < 1:
        continue
    for rate in [44100, 16000, 48000]:
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=min(2, info["maxInputChannels"]),
                rate=rate,
                input=True,
                input_device_index=i,
                frames_per_buffer=CHUNK
            )
            frames = b""
            for _ in range(10):   # ~0.5 s
                frames += stream.read(CHUNK, exception_on_overflow=False)
            stream.stop_stream(); stream.close()
            rms = audioop.rms(frames, 2)
            print(f"    Device [{i}] @ {rate} Hz  -> RMS = {rms}")
            rms_results[i] = (rate, rms)
            break  # found a working rate
        except Exception as ex:
            print(f"    Device [{i}] @ {rate} Hz  -> FAILED: {ex}")

# ── 4. Find best device ────────────────────────────────────────────
best_idx = max(rms_results, key=lambda k: rms_results[k][1], default=None)
if best_idx is not None:
    best_rate, best_rms = rms_results[best_idx]
    print(f"\n[4] Best device (highest RMS): [{best_idx}] @ {best_rate} Hz, RMS={best_rms}")
else:
    print("\n[4] No readable input device found!")
    pa.terminate()
    sys.exit(1)

# ── 5. Test sr.Microphone on the best device ───────────────────────
print(f"\n[5] Testing sr.Recognizer on device [{best_idx}] @ {best_rate} Hz ...")
print("    >>> SPEAK NOW for 4 seconds <<<\n")
time.sleep(0.5)

r = sr.Recognizer()
r.dynamic_energy_threshold = False
r.energy_threshold = 300   # very low - just capture ANYTHING
r.pause_threshold = 0.8

captured_rms = 0
captured_bytes = 0
text_result = ""

try:
    with sr.Microphone(device_index=best_idx, sample_rate=best_rate) as mic:
        print("    [Listening for up to 6 seconds - speak something...]")
        try:
            audio = r.listen(mic, timeout=6, phrase_time_limit=6)
            raw = audio.get_raw_data()
            captured_bytes = len(raw)
            captured_rms = audioop.rms(raw, 2)
            print(f"    Captured {captured_bytes} bytes, RMS={captured_rms}")

            # SpeechRecognition captures mono; resample using the rate carried
            # by this recording rather than assuming the hardware rate.
            resampled, _ = audioop.ratecv(
                raw, audio.sample_width, 1, audio.sample_rate, 16000, None
            )

            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(resampled)
            buf.seek(0)

            # Try Whisper
            try:
                from faster_whisper import WhisperModel
                print("    Loading Whisper tiny.en ...")
                wm = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                segs, info = wm.transcribe(buf, beam_size=1)
                text_result = " ".join(s.text for s in segs).strip()
                print(f"    Whisper lang_prob={info.language_probability:.2f}")
                print(f"    Whisper result: '{text_result}'")
            except Exception as we:
                print(f"    Whisper error: {we}")

        except sr.WaitTimeoutError:
            print("    TIMEOUT - no speech detected above threshold 300")
        except Exception as ex:
            print(f"    sr.listen error: {ex}")
except Exception as ex:
    print(f"    sr.Microphone open error: {ex}")

# ── Summary ────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  SUMMARY")
print("=" * 65)
print(f"  Best input device   : [{best_idx}] @ {best_rate} Hz")
print(f"  Captured bytes      : {captured_bytes}")
print(f"  Captured RMS        : {captured_rms}")
print(f"  Whisper transcript  : '{text_result}'")
print()
if captured_rms == 0:
    print("  VERDICT: Mic captured NOTHING. Wrong device or mic muted.")
elif not text_result:
    print("  VERDICT: Audio captured but Whisper returned empty - resampling issue?")
else:
    print("  VERDICT: SUCCESS - pipeline working!")
print("=" * 65)

pa.terminate()
