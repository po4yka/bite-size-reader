#!/usr/bin/env python3
"""Generate PNG icons from the SVG source.

Requires: pip install cairosvg
Usage: python generate-icons.py
"""

from pathlib import Path

SIZES = [16, 48, 128]
SVG_PATH = Path(__file__).parent / "icon.svg"


def main() -> None:
    try:
        import cairosvg
    except ImportError:
        print("cairosvg not installed. Install with: pip install cairosvg")
        print(
            "Alternatively, open icon.svg in a browser and export as PNG at 16x16, 48x48, 128x128."
        )
        return

    svg_data = SVG_PATH.read_bytes()
    for size in SIZES:
        out = SVG_PATH.parent / f"icon-{size}.png"
        cairosvg.svg2png(
            bytestring=svg_data, write_to=str(out), output_width=size, output_height=size
        )
        print(f"Generated {out.name} ({size}x{size})")


if __name__ == "__main__":
    main()
