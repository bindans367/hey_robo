"""Interactive microphone/Faster-Whisper check; no wake word or Gemini calls.

Run from the project root with `python test_mic_stt.py` (or `--mic N`).
The operator speaks each prompt and scores the transcript for these real-room
conditions: regular, Indian English, long, short, pauses, background noise, and
low volume. This script requires a physical microphone to score acoustic quality.
"""
import argparse

import speech_recognition as sr

import voice_engine


SCENARIOS = [
    ("Normal English", "Say: What time does the library open, and where is it?"),
    ("Indian English", "In your usual Indian English accent, ask: Can you tell me about CSE placements at SIT Tumakuru?"),
    ("Long question", "Ask a 15 to 25 second question about admission, fees, hostel, or placements."),
    ("Short question", "Say clearly: Where is the main library?"),
    ("Speech with pauses", "Ask a question, pause for about one second in the middle, then finish the question."),
    ("Background noise", "With ordinary fan or room noise present, ask: How do I reach the admissions office?"),
    ("Low-volume speech", "From your normal position, speak softly (do not whisper): Where can I find the health centre?"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mic", type=int, help="PortAudio microphone index; default is Windows' current input")
    args = parser.parse_args()
    if args.mic is not None and args.mic < 0:
        parser.error("--mic must be a non-negative device index")
    if args.mic is not None:
        voice_engine.MIC_DEVICE_INDEX = args.mic

    device = "Windows default" if voice_engine.MIC_DEVICE_INDEX is None else str(voice_engine.MIC_DEVICE_INDEX)
    print("Robo standalone microphone/STT check — wake word and Gemini are disabled")
    print(f"Input device: {device}")
    try:
        with sr.Microphone(device_index=voice_engine.MIC_DEVICE_INDEX) as mic:
            print(f"Device sample rate: {mic.SAMPLE_RATE} Hz; SpeechRecognition captures mono PCM.")
    except Exception as exc:
        print(f"[ERROR] Microphone could not open: {type(exc).__name__}: {exc}")
        return 2

    voice_engine.calibrate_microphone()
    print("Speak when prompted. Use ordinary conversational volume and let the silence detector finish each turn.")
    print("The first turn loads the cached offline model; later turns reuse it.\n")

    results = []
    for index, (name, prompt) in enumerate(SCENARIOS, 1):
        go = input(f"[{index}/{len(SCENARIOS)}] {name}: {prompt}\nPress Enter, then speak (or type q to stop): ")
        if go.strip().lower() == "q":
            break
        transcript = voice_engine.listen(timeout=8, phrase_time_limit=30, offline_only=True)
        print(f"Recognized: {transcript or '[EMPTY]'}")
        score = input("Was the full transcript accurate? [y/N] ").strip().lower() == "y"
        results.append((name, bool(transcript), score))
        print()

    print("Results")
    for name, captured, accurate in results:
        print(f"{'PASS' if accurate else 'REVIEW'}  {name}: {'captured' if captured else 'empty'}")
    passed = sum(1 for _, _, accurate in results if accurate)
    print(f"Operator-scored accuracy: {passed}/{len(results)}")
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
