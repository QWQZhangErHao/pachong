"""Mouse trajectory + keystroke simulation — GAN noise, phase randomization, Chinese support."""

from __future__ import annotations

import math
import random
import time


def _bezier(p0, p1, p2, p3, steps=30):
    """Cubic Bezier with GAN-style second-derivative jitter."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        jitter = random.gauss(0, 0.3) * (1 + 2 * abs(t - 0.5))
        pts.append((round(x + jitter, 1), round(y + jitter, 1)))
    return pts


def generate_trajectory(x1, y1, x2, y2, duration_ms=800, steps=30):
    """Human mouse trajectory with random control points + overshoot correction."""
    cp1x = x1 + random.randint(50, 200) * random.choice([-1, 1])
    cp1y = y1 + random.randint(-50, 150)
    cp2x = x2 + random.randint(-100, 100)
    cp2y = y2 + random.randint(-100, 50)
    pts = _bezier((x1, y1), (cp1x, cp1y), (cp2x, cp2y), (x2, y2), steps)
    if random.random() < 0.3:
        last = pts[-1]
        pts.append((last[0] + random.randint(-3, 3), last[1] + random.randint(-3, 3)))
    return pts


def generate_click(x, y):
    delay = random.randint(30, 150)
    return [("mousedown", x, y, delay), ("mouseup", x, y, random.randint(20, 80))]


def generate_random_delay():
    return max(100, min(3000, int(random.lognormvariate(6.5, 0.6))))


def generate_hover_trajectory(target, duration_ms=800):
    return _bezier(
        (target[0] + random.randint(50, 200), target[1] + random.randint(-50, 50)),
        (target[0] + random.randint(20, 80), target[1] + random.randint(-20, 20)),
        (target[0] + random.randint(-10, 10), target[1] + random.randint(-10, 10)),
        target, max(10, duration_ms // 30),
    )
