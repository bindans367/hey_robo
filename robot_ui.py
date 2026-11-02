"""
robot_ui.py - Terminal Visual Dashboard for SIT Humanoid Robot.
Provides clean status indicators, ASCII robot expressions, and formatted interaction logs.
"""

import sys
import os

ROBOT_FACES = {
    "READY": r"""
      .-------------------------.
      |        [o]   [o]        |
      |             ^           |
      |          \_____/        |
      '-------------------------'
    """,
    "LISTENING": r"""
      .-------------------------.
      |       [(o)] [(o)]       |
      |             ^           |
      |           (---)         |
      '-------------------------'
    """,
    "THINKING": r"""
      .-------------------------.
      |        [*]   [*]        |
      |             ^           |
      |           ~~~~~         |
      '-------------------------'
    """,
    "SPEAKING": r"""
      .-------------------------.
      |        [^]   [^]        |
      |             ^           |
      |          \==O==/        |
      '-------------------------'
    """
}


def print_banner(mode: str = "VOICE", topic_count: int = 58):
    """Displays the initial welcoming dashboard banner."""
    print("=" * 68)
    print("        SIDDAGANGA INSTITUTE OF TECHNOLOGY, TUMAKURU")
    print("              HUMANOID CAMPUS ASSISTANT ROBOT")
    print("                   [100% OFFLINE SYSTEM]")
    print("=" * 68)
    print(f"  System Status : ONLINE (OFFLINE MODE)   | Mode: {mode.upper()}")
    print(f"  Knowledge Base: {topic_count} Topics Loaded       | Audio: Active")
    print("-" * 68)


def show_robot_state(state: str, message: str = ""):
    """Renders the robot face corresponding to current state."""
    face = ROBOT_FACES.get(state, ROBOT_FACES["READY"])
    print(face)
    print(f"  >>> STATUS: [{state}] {message}\n")


def display_turn(user_query: str, title: str, confidence: float, answer: str, suggestions: list = None):
    """Prints a structured record of the Q&A turn."""
    print("-" * 68)
    print(f"  [STUDENT]   : {user_query}")
    print(f"  [MATCHED]   : {title} ({confidence}% confidence)")
    print(f"  [ROBOT]     : {answer}")
    if suggestions and len(suggestions) > 0:
        print(f"  [SUGGESTED] : {', '.join(suggestions[:3])}")
    print("-" * 68)


if __name__ == "__main__":
    print_banner()
    show_robot_state("READY", "Awaiting questions...")
    show_robot_state("LISTENING", "Listening for student speech...")
    show_robot_state("SPEAKING", "Answering query...")
