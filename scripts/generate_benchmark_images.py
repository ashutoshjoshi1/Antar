"""Generate the sample images used by the vision benchmark workload.

The images are drawn from scratch by this script (no third-party content) and
are dedicated to the public domain under CC0 1.0. Pure standard library, so it
runs anywhere:

    uv run python scripts/generate_benchmark_images.py
"""

import struct
import zlib
from collections.abc import Callable
from pathlib import Path

SIZE = 256
Color = tuple[int, int, int]
Painter = Callable[[int, int], Color]

WHITE: Color = (255, 255, 255)
BLACK: Color = (20, 20, 20)
RED: Color = (220, 40, 40)
GREEN: Color = (40, 170, 70)
BLUE: Color = (40, 90, 220)
YELLOW: Color = (240, 200, 30)
ORANGE: Color = (240, 140, 30)
DARK: Color = (45, 45, 55)

ASSETS = Path(__file__).resolve().parent.parent / "antar" / "benchmarking" / "assets"


def write_png(path: Path, painter: Painter) -> None:
    rows = b"".join(
        b"\x00" + bytes(channel for x in range(SIZE) for channel in painter(x, y))
        for y in range(SIZE)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def in_circle(x: int, y: int, cx: int, cy: int, radius: int) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def shapes(x: int, y: int) -> Color:
    """A red circle, a blue square, and a green triangle on white."""
    if in_circle(x, y, 52, 128, 34):
        return RED
    if 94 <= x <= 162 and 94 <= y <= 162:
        return BLUE
    if 94 <= y <= 162 and abs(x - 208) <= (y - 94) * 34 // 68:
        return GREEN
    return WHITE


def bar_chart(x: int, y: int) -> Color:
    """Four bars of increasing height: blue, orange, green, red."""
    baseline = 220
    if (y in (baseline, baseline + 1) and 24 <= x <= 236) or (
        x in (24, 25) and 30 <= y <= baseline
    ):
        return BLACK
    bars = ((44, 60, BLUE), (92, 100, ORANGE), (140, 140, GREEN), (188, 180, RED))
    for left, height, color in bars:
        if left <= x < left + 32 and baseline - height <= y < baseline:
            return color
    return WHITE


def traffic_light(x: int, y: int) -> Color:
    """A dark housing with red, yellow, and green lamps stacked top to bottom."""
    for cy, color in ((62, RED), (128, YELLOW), (194, GREEN)):
        if in_circle(x, y, 128, cy, 26):
            return color
    if 84 <= x <= 172 and 20 <= y <= 236:
        return DARK
    return WHITE


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, painter in (
        ("shapes.png", shapes),
        ("bar-chart.png", bar_chart),
        ("traffic-light.png", traffic_light),
    ):
        write_png(ASSETS / name, painter)
