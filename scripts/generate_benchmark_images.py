"""Generate the sample images used by the vision benchmark workloads.

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


# A 5x7 bitmap font for the characters the document and diagram images use.
FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    " ": ("00000",) * 7,
}

# Text shown in document.png. The reference answers in the workloads are these strings.
DOCUMENT_LINES = ("INVOICE 4821", "DATE 2026-03-14", "TOTAL 137.50")
# Boxes in diagram.png, left to right; an arrow joins each box to the next.
DIAGRAM_BOXES = ("API", "CPU", "GPU")


def text_pixel(x: int, y: int, text: str, left: int, top: int, scale: int) -> bool:
    """Whether (x, y) is an inked pixel of ``text`` drawn at (left, top)."""
    column, row = (x - left) // scale, (y - top) // scale
    if x < left or y < top or row >= 7:
        return False
    index, offset = divmod(column, 6)
    if index >= len(text) or offset >= 5:
        return False
    return FONT[text[index]][row][offset] == "1"


def document(x: int, y: int) -> Color:
    """Three lines of dark text on white, like a scanned receipt."""
    for line_number, line in enumerate(DOCUMENT_LINES):
        if text_pixel(x, y, line, 14, 50 + line_number * 60, 2 if len(line) > 12 else 3):
            return BLACK
    return WHITE


def diagram(x: int, y: int) -> Color:
    """Three labelled boxes in a row, joined left to right by arrows."""
    for index, label in enumerate(DIAGRAM_BOXES):
        left = 10 + index * 86
        if text_pixel(x, y, label, left + 9, 117, 3):
            return BLACK
        inside = left <= x <= left + 64 and 100 <= y <= 156
        if inside and (x in (left, left + 1, left + 63, left + 64) or y in (100, 101, 155, 156)):
            return BLUE
        if index < len(DIAGRAM_BOXES) - 1:
            start, end = left + 65, left + 85
            if start <= x <= end and y in (127, 128, 129):
                return BLACK
            if end - 7 <= x <= end and abs(y - 128) <= end - x:
                return BLACK
    return WHITE


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, painter in (
        ("shapes.png", shapes),
        ("bar-chart.png", bar_chart),
        ("traffic-light.png", traffic_light),
        ("document.png", document),
        ("diagram.png", diagram),
    ):
        write_png(ASSETS / name, painter)
