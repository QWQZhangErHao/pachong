"""Keystroke dynamics simulation.

Real humans have distinct typing patterns:
- Variable inter-key delays (common letters typed faster)
- Occasional backspaces with correction
- Different speeds for different text types (URL vs search query vs form)
"""

from __future__ import annotations

import random
import time


# Average typing speed: ~200ms per keystroke for average typist
# Common letter pairs (bigrams) have shorter inter-key delays
FAST_BIGRAMS = {
    "th", "he", "in", "er", "an", "on", "at", "en", "nd", "ti",
    "es", "or", "te", "of", "ed", "is", "it", "al", "ar", "st",
}

# Keys typed with the same finger have longer delays
SAME_FINGER_KEYS = {
    ("q", "a"), ("a", "z"), ("w", "s"), ("s", "x"), ("e", "d"),
    ("d", "c"), ("r", "f"), ("f", "v"), ("t", "g"), ("g", "b"),
    ("y", "h"), ("h", "n"), ("u", "j"), ("j", "m"), ("i", "k"),
    ("o", "l"), ("p", ";"),
}


def generate_typing_sequence(
    text: str,
    typing_style: str = "normal",
) -> list[dict]:
    """Generate a human-like typing sequence.

    Returns list of {type: "keydown"/"keyup", key, delayMs}

    Args:
        text: The text to type
        typing_style: "hunt_and_peck", "normal", "fast", "search", "url"
    """
    style_params = {
        "hunt_and_peck": {"base_delay": 400, "variance": 200, "error_rate": 0.05},
        "normal": {"base_delay": 200, "variance": 100, "error_rate": 0.02},
        "fast": {"base_delay": 120, "variance": 60, "error_rate": 0.01},
        "search": {"base_delay": 180, "variance": 120, "error_rate": 0.03},
        "url": {"base_delay": 150, "variance": 80, "error_rate": 0.01},
    }
    params = style_params.get(typing_style, style_params["normal"])

    events: list[dict] = []
    prev_char = ""

    for i, char in enumerate(text):
        # Determine delay before this keystroke
        delay = _get_keystroke_delay(prev_char, char, params)

        # Simulate occasional typo + backspace + correction
        if random.random() < params["error_rate"] and char.isalpha():
            wrong_char = _get_adjacent_key(char)
            if wrong_char:
                # Type wrong key
                events.append({"type": "keydown", "key": wrong_char, "delayMs": delay})
                events.append({"type": "keyup", "key": wrong_char, "delayMs": 50})
                # Backspace
                events.append({"type": "keydown", "key": "Backspace", "delayMs": 150})
                events.append({"type": "keyup", "key": "Backspace", "delayMs": 50})
                # Correct key
                delay = random.uniform(50, 150)

        events.append({"type": "keydown", "key": char, "delayMs": delay})
        events.append({"type": "keyup", "key": char, "delayMs": random.uniform(30, 80)})

        prev_char = char.lower()

    return events


def _get_keystroke_delay(prev: str, current: str, params: dict) -> float:
    """Calculate realistic inter-keystroke delay."""
    base = params["base_delay"]
    variance = params["variance"]

    # Fast bigrams → shorter delay
    bigram = (prev + current).lower()
    if bigram in FAST_BIGRAMS:
        base *= 0.6

    # Same finger keys → longer delay
    pair = (prev.lower(), current.lower())
    if pair in SAME_FINGER_KEYS or pair[::-1] in SAME_FINGER_KEYS:
        base *= 1.5

    # After space/punctuation → slight pause
    if prev in (" ", ".", ",", "!", "?"):
        base *= 1.3

    # Shift key adds delay
    if current.isupper() or current in "!@#$%^&*()_+{}|:\"<>?":
        base *= 1.2

    return max(30, random.gauss(base, variance))


def _get_adjacent_key(char: str) -> str | None:
    """Return a physically adjacent key on QWERTY keyboard (for typo simulation)."""
    adjacent = {
        "a": "s", "b": "n", "c": "x", "d": "f", "e": "r",
        "f": "g", "g": "h", "h": "j", "i": "o", "j": "k",
        "k": "l", "l": "k", "m": "n", "n": "b", "o": "i",
        "p": "o", "q": "w", "r": "t", "s": "d", "t": "y",
        "u": "i", "v": "b", "w": "e", "x": "c", "y": "t",
        "z": "x",
    }
    return adjacent.get(char.lower(), None)
