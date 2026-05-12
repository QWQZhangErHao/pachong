"""Behavior orchestration — coordinates mouse, scroll, and typing into
complete human-like interaction scripts.

A conductor script is a timeline of events that can be injected into
Playwright or Puppeteer to simulate realistic user behavior.
"""

from __future__ import annotations

import random
import time

from pachong.anti_detect.behavior.mouse import (
    generate_click,
    generate_hover_trajectory,
    generate_random_delay,
    generate_trajectory,
)
from pachong.anti_detect.behavior.scroll import generate_scroll_sequence, generate_wheel_events
from pachong.anti_detect.behavior.typing import generate_typing_sequence


def generate_page_visit_script(
    page_type: str = "product",
    duration_ms: float | None = None,
) -> list[dict]:
    """Generate a complete human-like page interaction script.

    Script phases:
    1. Page load (natural delay)
    2. Initial scanning (scroll overview)
    3. Focused reading (slower scroll with pauses)
    4. Possible interaction (click/hover)
    5. Exit

    Args:
        page_type: "product", "listing", "search", "article"
        duration_ms: Total visit duration. Auto-computed if None.

    Returns:
        List of event dicts: {type, phase, ...phase-specific fields, delayMs}
    """
    if duration_ms is None:
        duration_ms = random.uniform(3000, 15000)  # 3-15 seconds

    events: list[dict] = []
    current_time = 0.0

    # Phase 1: Page load (natural initial delay)
    load_delay = random.uniform(500, 2000)
    current_time += load_delay
    events.append({"type": "pause", "phase": "load", "durationMs": load_delay, "time": current_time})

    # Phase 2: Initial scanning scroll (fast overview)
    scroll_px = random.randint(300, 800)
    scan_scrolls = generate_scroll_sequence(scroll_px, "listing", 2000)
    for pos, delay in scan_scrolls:
        current_time += delay
        events.append({
            "type": "scroll",
            "phase": "scanning",
            "position": pos,
            "delayMs": delay,
            "time": current_time,
        })

    # Phase 3: Random mouse movement (exploring the page)
    if random.random() < 0.8:
        start_pos = (random.randint(200, 800), random.randint(200, 600))
        end_pos = (random.randint(400, 1200), random.randint(300, 700))
        trajectory = generate_trajectory(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
        for x, y, t in trajectory:
            current_time += 16.67  # ~60Hz
            events.append({
                "type": "mousemove",
                "phase": "exploring",
                "x": x,
                "y": y,
                "delayMs": 16.67,
                "time": current_time,
            })

    # Phase 4: Detailed scroll (reading)
    detail_scroll_px = random.randint(200, 600)
    detail_scrolls = generate_scroll_sequence(detail_scroll_px, "product", 4000)
    for pos, delay in detail_scrolls:
        current_time += delay
        events.append({
            "type": "scroll",
            "phase": "reading",
            "position": pos,
            "delayMs": delay,
            "time": current_time,
        })

    # Phase 5: Hover interaction (examining something)
    if random.random() < 0.6:
        hover_x = random.randint(300, 1000)
        hover_y = random.randint(200, 600)
        hover_points = generate_hover_trajectory((hover_x, hover_y), random.uniform(500, 2000))
        for x, y, t in hover_points:
            current_time += t
            events.append({
                "type": "mousemove",
                "phase": "hovering",
                "x": x,
                "y": y,
                "delayMs": t,
                "time": current_time,
            })

    # Phase 6: Possible click
    if random.random() < 0.4:
        click_events = generate_click(random.randint(300, 1000), random.randint(200, 600))
        for event_type, x, y, delay in click_events:
            current_time += delay
            events.append({
                "type": event_type,
                "phase": "interacting",
                "x": x,
                "y": y,
                "delayMs": delay,
                "time": current_time,
            })

    # Phase 7: Exit delay
    exit_delay = random.uniform(200, 1000)
    current_time += exit_delay
    events.append({"type": "pause", "phase": "exit", "durationMs": exit_delay, "time": current_time})

    return events


def generate_search_script(query: str, input_selector: str = "#search") -> list[dict]:
    """Generate a search interaction script: click search box, type query, submit."""
    events = []
    current_time = 0.0

    # Move mouse to search box
    trajectory = generate_trajectory(500, 300, 600, 100, duration_ms=800)
    for x, y, t in trajectory:
        current_time += 16.67
        events.append({"type": "mousemove", "x": x, "y": y, "time": current_time})

    # Click search box
    for event_type, x, y, delay in generate_click(600, 100):
        current_time += delay
        events.append({"type": event_type, "x": x, "y": y, "time": current_time})

    # Type query
    keystrokes = generate_typing_sequence(query, "search")
    for ks in keystrokes:
        current_time += ks["delayMs"]
        events.append({**ks, "time": current_time})

    # Press Enter
    current_time += 200
    events.append({"type": "keydown", "key": "Enter", "time": current_time})
    current_time += 50
    events.append({"type": "keyup", "key": "Enter", "time": current_time})

    return events


def convert_to_puppeteer_script(events: list[dict]) -> str:
    """Convert behavior events to a Puppeteer JavaScript injection script."""
    lines = ["(async () => {"]
    for evt in events:
        etype = evt.get("type", "pause")
        delay = evt.get("delayMs", evt.get("time", 50))
        lines.append(f"  await new Promise(r => setTimeout(r, {delay}));")
        if etype == "mousemove":
            lines.append(f"  document.dispatchEvent(new MouseEvent('mousemove', {{clientX: {evt['x']}, clientY: {evt['y']}}}));")
        elif etype == "mousedown":
            lines.append(f"  document.dispatchEvent(new MouseEvent('mousedown', {{clientX: {evt['x']}, clientY: {evt['y']}, bubbles: true}}));")
        elif etype == "mouseup":
            lines.append(f"  document.dispatchEvent(new MouseEvent('mouseup', {{clientX: {evt['x']}, clientY: {evt['y']}, bubbles: true}}));")
        elif etype == "scroll":
            lines.append(f"  window.scrollTo(0, {evt['position']});")
        elif etype in ("keydown", "keyup"):
            lines.append(f"  document.dispatchEvent(new KeyboardEvent('{etype}', {{key: '{evt.get('key', '')}', bubbles: true}}));")
    lines.append("})();")
    return "\n".join(lines)
