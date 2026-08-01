"""Scroll pattern simulation.

Humans scroll in bursts with pauses (reading), not smooth continuous motion.
Patterns vary by content type: product pages get more methodical scrolling,
while listing pages get rapid skimming.
"""

from __future__ import annotations

import random


def generate_scroll_sequence(
    total_scroll_px: float,
    page_type: str = "product",
    duration_estimate_ms: float | None = None,
) -> list[tuple[float, float]]:
    """Generate a human-like scroll sequence.

    Returns list of (scroll_position, delay_before_next_ms).

    Args:
        total_scroll_px: Total pixels to scroll
        page_type: "product" (methodical, more pauses) or "listing" (rapid skimming)
        duration_estimate_ms: Approximate total time. Auto-computed if None.
    """
    if page_type == "product":
        return _product_page_scroll(total_scroll_px, duration_estimate_ms)
    elif page_type == "listing":
        return _listing_page_scroll(total_scroll_px, duration_estimate_ms)
    else:
        return _generic_scroll(total_scroll_px)


def _product_page_scroll(total_px: float, duration_ms: float | None = None) -> list[tuple[float, float]]:
    """Product page scrolling: slow, methodical, frequent pauses to 'read'."""
    # Number of scroll bursts (3-8)
    num_bursts = random.randint(max(2, int(total_px / 400)), max(4, int(total_px / 200)))
    burst_size = total_px / num_bursts
    sequence: list[tuple[float, float]] = []

    current_position = 0.0
    for i in range(num_bursts):
        # Vary burst size (sometimes scroll more, sometimes less)
        actual_burst = burst_size * random.uniform(0.6, 1.4)

        # Reading pause: 1-5 seconds on product pages
        if i > 0:
            pause_ms = random.uniform(1000, 5000)
            sequence.append((current_position, pause_ms))

        # Scroll duration for this burst
        scroll_duration_ms = actual_burst * 0.5 + random.uniform(100, 500)

        # Subdivide burst into micro-scrolls with momentum
        sub_steps = random.randint(3, 8)
        sub_size = actual_burst / sub_steps
        for j in range(sub_steps):
            # Decelerating sub-steps (momentum scroll)
            momentum = 1.0 - (j / sub_steps) * 0.6
            current_position += sub_size * momentum
            seq_delay = scroll_duration_ms / sub_steps + random.uniform(-20, 50)
            sequence.append((current_position, max(10, seq_delay)))

    # Final pause at bottom
    sequence.append((current_position, random.uniform(1000, 3000)))

    return sequence


def _listing_page_scroll(total_px: float, duration_ms: float | None = None) -> list[tuple[float, float]]:
    """Listing page scrolling: faster, fewer pauses, 'skimming' behavior."""
    num_bursts = random.randint(max(2, int(total_px / 600)), max(3, int(total_px / 300)))
    burst_size = total_px / num_bursts
    sequence: list[tuple[float, float]] = []

    current_position = 0.0
    for i in range(num_bursts):
        actual_burst = burst_size * random.uniform(0.7, 1.2)

        # Short pause between bursts (listing users skim fast)
        if i > 0:
            pause_ms = random.uniform(300, 1500)
            sequence.append((current_position, pause_ms))

        # Fast scroll
        scroll_duration_ms = actual_burst * 0.2 + random.uniform(50, 200)
        sub_steps = random.randint(2, 5)
        sub_size = actual_burst / sub_steps
        for j in range(sub_steps):
            current_position += sub_size
            sequence.append((current_position, max(10, scroll_duration_ms / sub_steps)))

    sequence.append((current_position, random.uniform(500, 2000)))
    return sequence


def _generic_scroll(total_px: float) -> list[tuple[float, float]]:
    """Generic scrolling behavior."""
    num_bursts = random.randint(3, 6)
    burst_size = total_px / num_bursts
    sequence = []

    pos = 0.0
    for i in range(num_bursts):
        if i > 0:
            sequence.append((pos, random.uniform(500, 2500)))
        pos += burst_size * random.uniform(0.8, 1.2)
        sub_steps = random.randint(2, 6)
        for _ in range(sub_steps):
            pos += burst_size / sub_steps * 0.3
            sequence.append((pos, random.uniform(20, 80)))

    sequence.append((total_px, random.uniform(1000, 3000)))
    return sequence


def generate_wheel_events(
    scroll_sequence: list[tuple[float, float]],
) -> list[dict]:
    """Convert scroll positions into discrete wheel events for browser injection.

    Returns list of {type: "wheel", deltaY, deltaX, clientX, clientY, delayMs}
    """
    events = []
    prev_pos = 0.0

    for position, delay_ms in scroll_sequence:
        delta_y = position - prev_pos
        prev_pos = position

        # Only emit wheel events for forward scrolling
        if delta_y > 0:
            # Subdivide large scrolls into multiple wheel events
            wheel_delta = 100  # Typical wheel delta
            num_events = max(1, int(delta_y / wheel_delta))

            for i in range(num_events):
                events.append({
                    "type": "wheel",
                    "deltaY": min(delta_y, wheel_delta),
                    "deltaX": 0,
                    "clientX": random.randint(500, 1400),  # Typical viewport center
                    "clientY": random.randint(200, 800),
                    "delayMs": delay_ms / num_events,
                })

    return events
