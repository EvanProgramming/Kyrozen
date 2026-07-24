#!/usr/bin/env python3
"""Generate PNG icons for the Kyrozen browser extension.

Uses only the Python standard library (zlib/struct) so it has no extra
dependencies. Run this script after changing the icon design.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Return a PNG chunk with length, type, data and CRC."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def create_png_rgba(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Create a minimal PNG from a flat list of RGBA tuples (top-to-bottom, left-to-right)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        for x in range(width):
            idx = y * width + x
            raw.extend(pixels[idx])
    compressed = zlib.compress(bytes(raw), level=9)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def _mix(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, int, int, int]:
    def _channel(idx: int) -> int:
        av = a[idx] if idx < len(a) else 255
        bv = b[idx] if idx < len(b) else 255
        return int(av + (bv - av) * t)
    return (_channel(0), _channel(1), _channel(2), _channel(3))


def render_k_icon(size: int) -> list[tuple[int, int, int, int]]:
    """Render a rounded 'K' on a gradient background."""
    # Palette
    bg_top = (59, 130, 246)       # blue-500
    bg_bottom = (37, 99, 235)     # blue-600
    k_color = (255, 255, 255, 255)
    shadow = (0, 0, 0, 40)

    pixels: list[tuple[int, int, int, int]] = []
    radius = size * 0.18
    center_x = size / 2
    center_y = size / 2

    # Anti-aliased by supersampling 4x then averaging.
    ss = 4
    for y in range(size):
        for x in range(size):
            r_total = g_total = b_total = a_total = 0
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss
                    py = y + (sy + 0.5) / ss
                    # Vertical gradient background
                    t = py / size
                    bg = _mix(bg_top, bg_bottom, t)

                    # Rounded rectangle mask
                    dx = abs(px - center_x) - (size / 2 - radius)
                    dy = abs(py - center_y) - (size / 2 - radius)
                    dist = max(dx, dy, 0.0)
                    corner_alpha = 1.0 - max(0.0, min(1.0, dist))

                    # Simple "K" shape (two diagonal strokes + vertical bar)
                    # Scale stroke width with icon size
                    stroke = max(1.5, size * 0.12)
                    # Vertical bar on the left
                    bar_x = size * 0.30
                    in_bar = abs(px - bar_x) < stroke / 2 and size * 0.22 < py < size * 0.78

                    # Upper diagonal \
                    ux1, uy1 = bar_x + stroke / 2, center_y - stroke / 3
                    ux2, uy2 = size * 0.72, size * 0.24
                    in_upper = _point_line_distance(px, py, ux1, uy1, ux2, uy2) < stroke / 2 and py <= center_y

                    # Lower diagonal /
                    lx1, ly1 = bar_x + stroke / 2, center_y + stroke / 3
                    lx2, ly2 = size * 0.72, size * 0.76
                    in_lower = _point_line_distance(px, py, lx1, ly1, lx2, ly2) < stroke / 2 and py >= center_y

                    in_k = in_bar or in_upper or in_lower

                    # Drop shadow under K
                    in_shadow = _point_line_distance(px - 1, py - 1, ux1, uy1, ux2, uy2) < stroke / 2 and py <= center_y
                    in_shadow |= _point_line_distance(px - 1, py - 1, lx1, ly1, lx2, ly2) < stroke / 2 and py >= center_y
                    in_shadow |= abs((px - 1) - bar_x) < stroke / 2 and size * 0.22 < (py - 1) < size * 0.78

                    if in_k:
                        color = k_color
                    elif in_shadow and not in_k:
                        color = shadow
                    else:
                        color = bg

                    r_total += color[0]
                    g_total += color[1]
                    b_total += color[2]
                    a_total += int(color[3] * corner_alpha)
            samples = ss * ss
            pixels.append((
                r_total // samples,
                g_total // samples,
                b_total // samples,
                a_total // samples,
            ))
    return pixels


def _point_line_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Return perpendicular distance from point to line segment."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5


def main() -> None:
    out_dir = Path(__file__).parent
    sizes = [16, 48, 128]
    for size in sizes:
        pixels = render_k_icon(size)
        png = create_png_rgba(size, size, pixels)
        out_path = out_dir / f"icon{size}.png"
        out_path.write_bytes(png)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
