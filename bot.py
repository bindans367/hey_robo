"""
bot.py - Master Offline Humanoid Robot Campus Assistant for SIT Tumkur.

Features:
- 100% Offline Speech Recognition via Faster-Whisper Transformer + Vosk Fallback
- Offline spoken answers through Windows SAPI (pyttsx3 fallback) with acronym expansion
- Multi-tier phonetic & accent matching (normalizer.py + matcher.py)
- Ingests website data & PDF documents
- Supports Hands-free Voice Mode, Push-to-Talk Mode, and Text Mode

Usage:
    python bot.py           # Launch Hands-Free Voice Mode (Continuous Listening)
    python bot.py --ptt     # Launch Push-to-Talk Voice Mode (Press Enter to Speak)
    python bot.py --mic 2   # Use PortAudio input device 2 instead of Windows default
    Say "Hey Robo" to wake the hands-free assistant; say "Robo stop" to exit.
    python bot.py --text    # Launch Text Mode for testing or keyboard input
    python bot.py --test    # Run automated pronunciation verification suite
    python bot.py --scrape  # Scrape and refresh data from sit.ac.in
    python bot.py --ingest <file.pdf> # Ingest new college PDF document
"""

import argparse
import sys
import os
import re
import atexit

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from matcher import matcher
from robo_brain_core import answer_query, claim_microphone_turn, get_settings, publish_runtime
from robot_ui import print_banner, show_robot_state, display_turn

_BOT_LOCK_HANDLE = None

def acquire_bot_lock():
    """Allow only one voice/text bot to own the microphone and speaker."""
    global _BOT_LOCK_HANDLE
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "robo_bot.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    handle = open(lock_path, "a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b" ")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError):
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()).encode("ascii"))
    handle.flush()
    _BOT_LOCK_HANDLE = handle
    atexit.register(handle.close)
    return True


def _announce_answer_mode(result):
    if result.get("notice"):
        print(f"  [MODE] {result['notice']}", flush=True)
        result["answer"] = result["notice"] + " " + result.get("answer", "")


def run_voice_mode(push_to_talk: bool = False):
    """Voice interaction loop for humanoid robot (continuous or push-to-talk)."""
    import voice_engine

    microphone = get_settings()["microphone"]
    voice_engine.MIC_DEVICE_INDEX = None if microphone["device_index"] < 0 else microphone["device_index"]
    voice_engine.recognizer.energy_threshold = microphone["energy_threshold"]
    voice_engine.calibrate_microphone()
    mode_str = "VOICE (PUSH-TO-TALK)" if push_to_talk else "VOICE (HANDS-FREE)"
    print_banner(mode=mode_str, topic_count=len(matcher.knowledge) + len(matcher.website_pages))

    conversation = get_settings()["conversation"]
    greeting = conversation["welcome"]
    show_robot_state("SPEAKING", "Greeting students...")
    publish_runtime("GREETING", answer=greeting, detail="Welcoming students.")
    voice_engine.speak(greeting)

    awake = push_to_talk
    ready_message = "Press Enter when you’re ready to ask." if push_to_talk else f"Say '{conversation['wake_phrases'][0]}' whenever you need a hand."
    show_robot_state("READY", ready_message)

    try:
        while True:
            if push_to_talk:
                try:
                    input("\n>>> Press [ENTER] when ready to speak (or Ctrl+C to quit)... ")
                except (EOFError, KeyboardInterrupt):
                    break

            conversation = get_settings()["conversation"]
            microphone = get_settings()["microphone"]
            voice_engine.MIC_DEVICE_INDEX = None if microphone["device_index"] < 0 else microphone["device_index"]
            prompt = f"Listening for {conversation['wake_phrases'][0]} or a SIT question..." if not awake else "Listening for your next question..."
            show_robot_state("LISTENING", prompt)
            publish_runtime("LISTENING", detail=prompt + " The transcript will appear when the utterance is recognized.")
            user_speech = voice_engine.listen(timeout=conversation["listen_timeout"], phrase_time_limit=conversation["phrase_time_limit"])

            if not user_speech:
                if push_to_talk:
                    print("  [INFO] No speech detected after pressing Enter. Try speaking louder or closer.")
                continue

            command = re.sub(r"[^\w\s]", " ", user_speech.lower())
            command = " ".join(command.split())
            publish_runtime("TRANSCRIPT", transcript=user_speech, detail="Speech recognized.")

            # Stop commands work whether the assistant is awake or waiting.
            stop_phrases = conversation["stop_phrases"]
            if any(command == phrase or command.startswith(phrase + " ") for phrase in stop_phrases):
                show_robot_state("SPEAKING", "Bidding farewell...")
                publish_runtime("SPEAKING", transcript=user_speech, answer=conversation["farewell"], detail="Robo is saying goodbye.")
                voice_engine.speak(conversation["farewell"])
                break

            wake_phrases = sorted(conversation["wake_phrases"], key=len, reverse=True)
            wake_phrase = next(
                (phrase for phrase in wake_phrases
                 if command == phrase or command.startswith(phrase + " ")),
                None,
            )
            if not awake and wake_phrase is None:
                # In sleep mode only the explicit wake phrase is actionable.
                # This prevents nearby conversation from waking the robot.
                print("  [WAKE] Sleeping; waiting for 'Hey Robo'.")
                continue
            if wake_phrase is not None:
                awake = True
                command = command[len(wake_phrase):].strip(" .,!?;:")
                show_robot_state("READY", "Robo is awake and listening.")
                if not command:
                    voice_engine.play_wake_sound()
                    publish_runtime("READY", transcript=user_speech, detail="Wake phrase heard. Robo is listening for your question.")
                    show_robot_state("LISTENING", "Wake phrase heard; waiting for the question.")
                    continue
                voice_engine.play_wake_sound()

            if not command:
                continue

            # If two dashboard-launched bot processes briefly overlap, only
            # the first one should answer and speak a near-identical utterance.
            if not claim_microphone_turn(command):
                print("  [INFO] Duplicate microphone turn suppressed.", flush=True)
                continue

            show_robot_state("THINKING", f"Recognized: '{command}' - Processing query...")
            publish_runtime("THINKING", transcript=command, detail="Finding the best answer in Robo’s knowledge.")
            res = answer_query(command, matcher, source="robot-microphone")
            _announce_answer_mode(res)

            display_turn(
                user_query=command,
                title=res["title"],
                confidence=res["confidence"],
                answer=res["answer"],
                suggestions=res.get("suggestions", [])
            )

            show_robot_state("SPEAKING", f"Answering '{res['title']}'...")
            publish_runtime("SPEAKING", transcript=command, answer=res["answer"], title=res["title"], detail="Robo is speaking this answer.")
            completed = voice_engine.speak(res["answer"])
            if completed is not False and not push_to_talk:
                # Return to wake-word-only sleep shortly after each answer.
                time.sleep(conversation["sleep_after_answer"])
                awake = False
            phase = "READY" if completed is not False else "INTERRUPTED"
            detail = "Sleeping; say Hey Robo to ask another question." if not awake and not push_to_talk else ("Ready for the next question." if completed is not False else "Speech was interrupted by the operator.")
            publish_runtime(phase, transcript=command, answer=res["answer"], title=res["title"], detail=detail)
            show_robot_state("READY", "Sleeping; say Hey Robo to ask another question." if not awake and not push_to_talk else "Ready for next question...")

    except KeyboardInterrupt:
        print("\n[INFO] Assistant shutdown requested by operator.")
    finally:
        publish_runtime("STOPPED", detail="Robot conversation has stopped.")
        voice_engine.cleanup()


def run_text_mode():
    """Interactive text / keyboard loop for testing or touchscreen terminal."""
    import voice_engine

    print_banner(mode="TEXT", topic_count=len(matcher.knowledge) + len(matcher.website_pages))
    print("Type your questions below. Type 'exit' or 'quit' to close.")
    print("Example queries:")
    print(" - 'Who is the principal of SIT?'")
    print(" - 'Tell me about highest package in placements'")
    print(" - 'What is the KCET cutoff code?'")
    print(" - 'Where is Birla auditorium?'")
    print(" - 'What are the boys hostel timings?'\n")

    while True:
        try:
            query = input("\n[STUDENT] Enter question > ").strip()
            if not query:
                continue

            if query.lower() in ["exit", "quit", "stop", "q"]:
                print("[ROBOT] Goodbye! Have a great day at SIT Tumakuru.")
                break

            res = answer_query(query, matcher, source="robot-text")
            _announce_answer_mode(res)
            display_turn(
                user_query=query,
                title=res["title"],
                confidence=res["confidence"],
                answer=res["answer"],
                suggestions=res.get("suggestions", [])
            )
            # Voice read-out in text mode
            voice_engine.speak(res["answer"])

        except (KeyboardInterrupt, EOFError):
            print("\nExiting assistant.")
            break
    voice_engine.cleanup()


def run_self_test():
    """Automated benchmark testing handling of regional accents and mistranscriptions."""
    test_cases = [
        ("who is principle of safety tumkur", "Principal of SIT"),
        ("where is bella auditor young", "Birla Auditorium"),
        ("tell me highest package in cse placement", "Placement Packages and Statistics"),
        ("what is boy hostal mess food like", "Hostel Mess and Dining"),
        ("when is hall sean cultural fest held", "Halcyon - Annual Cultural Fest"),
        ("k cet cutoff code for sit", "Engineering Admissions (KCET & COMEDK)"),
        ("how to reach sit from tumkur railway station", "How to Reach SIT"),
        ("who founded siddaganga mutt", "Founder - Dr. Sree Sree Shivakumara Swamigalu"),
        ("can i get management quota seat", "Management Quota Admissions"),
        ("what is minimum attendance required", "Attendance Requirement (85% Rule)"),
        ("where is central library and reading room", "Central Library"),
        ("what are labs in aiml department", "Artificial Intelligence & Machine Learning (AI & ML)"),
        ("is there an atm on campus", "Bank, ATM and Post Office"),
        ("tell me about robotics club robocore", "Student Clubs and Technical Societies"),
        ("what is the college timings and id card rule", "College Timings and Dress Code")
    ]

    print("\n" + "=" * 70)
    print("        RUNNING SIT ACCENT & PRONUNCIATION BENCHMARK SUITE")
    print("=" * 70)

    passed = 0
    for query, expected_topic in test_cases:
        res = matcher.search(query)
        match_ok = res["matched"] and (res["title"] == expected_topic)
        status_tag = "[PASS]" if match_ok else "[FAIL]"
        if match_ok:
            passed += 1

        print(f"{status_tag} Query : '{query}'")
        print(f"       Matched: '{res['title']}' ({res['confidence']}%) | Expected: '{expected_topic}'\n")

    accuracy = (passed / len(test_cases)) * 100
    print("-" * 70)
    print(f"BENCHMARK RESULT: {passed}/{len(test_cases)} Passed ({accuracy:.1f}% Accuracy)")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SIT Humanoid Robot Offline Campus Assistant")
    parser.add_argument("--text", action="store_true", help="Launch interactive text mode")
    parser.add_argument("--ptt", "--push-to-talk", action="store_true", help="Enable push-to-talk mode (press Enter to speak)")
    parser.add_argument("--mic", type=int, metavar="DEVICE_INDEX", help="Select a PortAudio microphone device (default: Windows default input)")
    parser.add_argument("--test", action="store_true", help="Run automated pronunciation test suite")
    parser.add_argument("--scrape", action="store_true", help="Scrape latest info from sit.ac.in")
    parser.add_argument("--ingest", type=str, help="Ingest a college PDF document")

    args = parser.parse_args()

    if args.mic is not None and args.mic < 0:
        parser.error("--mic must be a non-negative PortAudio device index")

    if not (args.scrape or args.ingest or args.test):
        if not acquire_bot_lock():
            print("[ERROR] Another Robo assistant is already active. Stop that instance before starting another.", file=sys.stderr)
            return 2

    if args.scrape:
        import scrape_sit
        scrape_sit.main()
    elif args.ingest:
        import ingest_pdf
        ingest_pdf.ingest_file(args.ingest)
    elif args.test:
        run_self_test()
    elif args.text:
        import voice_engine
        if args.mic is not None:
            voice_engine.MIC_DEVICE_INDEX = args.mic
        run_text_mode()
    else:
        # Default: Voice Mode (pass push_to_talk flag if set)
        import voice_engine
        if args.mic is not None:
            voice_engine.MIC_DEVICE_INDEX = args.mic
        run_voice_mode(push_to_talk=args.ptt)


if __name__ == "__main__":
    raise SystemExit(main())
