from __future__ import annotations
import math
import random
import time

SESSION_KEY = 'login_captcha'
LENGTH = 4
TTL_SEC = 300
WIDTH = 150
HEIGHT = 52
_rng = random.SystemRandom()
_GLYPHS = {
    '0': [[(5, 0), (8.5, 2), (10, 8), (8.5, 14), (5, 16), (1.5, 14), (0, 8), (1.5, 2), (5, 0)]],
    '1': [[(2, 3), (5, 0), (5, 16)], [(2, 16), (8, 16)]],
    '2': [[(0.5, 3), (3, 0), (7, 0), (9.5, 3), (9, 6.5), (0, 16), (10, 16)]],
    '3': [[(0.5, 1.5), (4, 0), (8, 0.5), (9.5, 3.5), (8, 7), (4, 8)], [(4, 8), (8.5, 9), (10, 12.5), (8, 15.5), (4, 16), (0.5, 14.5)]],
    '4': [[(7, 16), (7, 0), (0, 11), (10, 11)]],
    '5': [[(9.5, 0), (1.5, 0), (0.5, 7), (4, 6), (8, 6.5), (10, 10), (9, 14.5), (5, 16), (0.5, 14.5)]],
    '6': [[(8.5, 1), (5, 0), (1.5, 2.5), (0, 8), (0.5, 13), (4, 16), (8, 15), (10, 11.5), (8.5, 8), (4.5, 7.5), (1, 9.5)]],
    '7': [[(0, 0), (10, 0), (4, 16)]],
    '8': [
        [
            (5, 8),
            (1.5, 6.5),
            (1, 3),
            (3.5, 0.3),
            (6.5, 0.3),
            (9, 3),
            (8.5, 6.5),
            (5, 8),
            (1, 10.5),
            (0.5, 13.5),
            (3.5, 16),
            (6.5, 16),
            (9.5, 13.5),
            (9, 10.5),
            (5, 8),
        ]
    ],
    '9': [[(9, 6.5), (5.5, 8.5), (1.5, 7.5), (0, 4), (1.5, 1), (5, 0), (8.5, 1.5), (10, 6), (9, 11), (5.5, 15.5), (1.5, 15)]],
}


def new_code(session) -> str:
    code = ''.join((_rng.choice('0123456789') for _ in range(LENGTH)))
    session[SESSION_KEY] = {'code': code, 'at': time.time()}
    return code


def check(session, answer: str) -> bool:
    data = session.pop(SESSION_KEY, None)
    if not data or time.time() - data.get('at', 0) > TTL_SEC:
        return False
    return (answer or '').strip() == data.get('code')


def _glyph_path(glyph: list[list[tuple[float, float]]], ox: float, oy: float, scale: float, angle: float) -> str:
    cos_a, sin_a = (math.cos(angle), math.sin(angle))
    parts = []
    for stroke in glyph:
        points = []
        for x, y in stroke:
            x = (x - 5 + _rng.uniform(-0.35, 0.35)) * scale
            y = (y - 8 + _rng.uniform(-0.35, 0.35)) * scale
            points.append(f'{ox + x * cos_a - y * sin_a:.1f},{oy + x * sin_a + y * cos_a:.1f}')
        parts.append('M' + ' L'.join(points))
    return ' '.join(parts)


def render_svg(code: str) -> str:
    shapes = []
    for _ in range(45):
        shapes.append(
            f'<circle cx="{_rng.uniform(0, WIDTH):.1f}" cy="{_rng.uniform(0, HEIGHT):.1f}" r="{_rng.uniform(0.4, 1.3):.1f}" fill="#9aa0a6" opacity="{_rng.uniform(0.3, 0.8):.2f}"/>'
        )
    step = (WIDTH - 30) / len(code)
    for i, ch in enumerate(code):
        ox = 18 + step * i + step / 2 + _rng.uniform(-4, 4)
        oy = HEIGHT / 2 + _rng.uniform(-4, 4)
        scale = _rng.uniform(1.45, 1.75)
        angle = math.radians(_rng.uniform(-28, 28))
        shade = _rng.randint(55, 110)
        shapes.append(
            f'<path d="{_glyph_path(_GLYPHS[ch], ox, oy, scale, angle)}" fill="none" stroke="rgb({shade},{shade},{shade + 10})" stroke-width="{_rng.uniform(2.0, 2.8):.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for _ in range(2):
        y1, y2 = (_rng.uniform(10, HEIGHT - 10), _rng.uniform(10, HEIGHT - 10))
        cx1, cy1 = (_rng.uniform(30, 70), _rng.uniform(0, HEIGHT))
        cx2, cy2 = (_rng.uniform(80, 120), _rng.uniform(0, HEIGHT))
        shapes.append(
            f'<path d="M4,{y1:.1f} C{cx1:.1f},{cy1:.1f} {cx2:.1f},{cy2:.1f} {WIDTH - 4},{y2:.1f}" fill="none" stroke="#6b7078" stroke-width="1.4" opacity="0.8"/>'
        )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"><rect width="100%" height="100%" fill="#f4f5f7"/>{"".join(shapes)}</svg>'
