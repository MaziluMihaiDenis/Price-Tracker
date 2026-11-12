"""Draws price-tracker.ico: the app's green "P" mark (as in the sidebar), at 16, 32 and 48 px.

Standard library only. Re-run after changing the colours or shape:
    .venv\\Scripts\\python.exe scripts\\launcher\\make_icon.py
"""

import struct
from pathlib import Path

GREEN = (0x39, 0x7D, 0x61)  # --green in app.css
WHITE = (0xFF, 0xFF, 0xFF)
SIZES = (16, 32, 48)
SAMPLES = 4  # 4x4 samples per pixel, for smooth edges
OUT = Path(__file__).with_name("price-tracker.ico")


def in_rounded_square(x, y, radius=0.22):
    """The green tile: a square with rounded corners (coordinates 0..1)."""
    cx = min(max(x, radius), 1 - radius)
    cy = min(max(y, radius), 1 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def in_half_ellipse(x, y, cx, cy, rx, ry):
    return x >= cx and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def in_letter_p(x, y):
    """A bold "P": a stem plus a D-shaped bowl with a hole."""
    stem = 0.30 <= x <= 0.43 and 0.22 <= y <= 0.78
    bowl = (0.30 <= x <= 0.53 and 0.22 <= y <= 0.58) or in_half_ellipse(x, y, 0.53, 0.40, 0.17, 0.18)
    hole = (0.43 <= x <= 0.53 and 0.33 <= y <= 0.47) or in_half_ellipse(x, y, 0.53, 0.40, 0.065, 0.07)
    return stem or (bowl and not hole)


def pixel(size, px, py):
    """(r, g, b, a) for one pixel, averaging SAMPLES x SAMPLES points inside it."""
    tile = letter = 0
    for sx in range(SAMPLES):
        for sy in range(SAMPLES):
            x = (px + (sx + 0.5) / SAMPLES) / size
            y = (py + (sy + 0.5) / SAMPLES) / size
            if in_rounded_square(x, y):
                tile += 1
                letter += in_letter_p(x, y)
    total = SAMPLES * SAMPLES
    if not tile:
        return 0, 0, 0, 0
    mix = letter / tile
    r, g, b = (round(GREEN[i] * (1 - mix) + WHITE[i] * mix) for i in range(3))
    return r, g, b, round(255 * tile / total)


def bitmap(size):
    """One icon image in the classic ICO format: a 32-bit BMP without its file header."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for py in reversed(range(size)):  # BMP rows go bottom-up
        row = bytearray()
        for px in range(size):
            r, g, b, a = pixel(size, px, py)
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    mask_row = bytes(((size + 31) // 32) * 4)  # all zero: transparency comes from the alpha channel
    return header + b"".join(rows) + mask_row * size


def main():
    images = [bitmap(size) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = b""
    for size, image in zip(SIZES, images):
        directory += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
    OUT.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images))
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
