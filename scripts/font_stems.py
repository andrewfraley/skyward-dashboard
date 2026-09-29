"""Find font sizes that render evenly on a 1-bit display.

At one bit per pixel a stem 2.5 px wide comes out as a mix of 2 and 3 px, so the
same letter looks different from one place to the next. This renders stems the
way ESPHome's `bpp: 1` fonts do (FreeType, FT_LOAD_TARGET_MONO) and reports, for
each size, the commonest stem width and how many stems have it:

    esphome-venv/bin/python scripts/font_stems.py display/esphome/.esphome/font/Inter@600@False@v1.ttf
    esphome-venv/bin/python scripts/font_stems.py FONT.ttf --sizes 18-30 --min 0

ESPHome downloads a layout's gfonts:// fonts into display/esphome/.esphome/font/
when it builds. Pick sizes at 90% or more. Needs freetype-py, which the ESPHome
venv has.
"""

import argparse
import collections

import freetype

LETTERS = "HIlnmuUhitEF"  # mostly straight stems


def stems(path: str, size: int) -> tuple[int, int]:
    """(commonest stem width in px, percent of stems that width)."""
    face = freetype.Face(path)
    face.set_pixel_sizes(size, 0)
    runs = collections.Counter()
    for ch in LETTERS:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO)
        bm = face.glyph.bitmap
        for y in range(bm.rows):
            run = 0
            for x in range(bm.width + 1):
                if x < bm.width and bm.buffer[y * bm.pitch + x // 8] & (0x80 >> (x % 8)):
                    run += 1
                elif run:
                    runs[run] += 1
                    run = 0
    widths = {w: n for w, n in runs.items() if w <= 6}
    width, count = max(widths.items(), key=lambda kv: kv[1])
    return width, 100 * count // sum(widths.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fonts", nargs="+", help="TTF/OTF files")
    parser.add_argument("--sizes", default="14-48", help="a range of pixel sizes, e.g. 18-30")
    parser.add_argument("--min", type=int, default=88, help="only list sizes at least this even")
    args = parser.parse_args()
    low, high = map(int, args.sizes.split("-"))
    for path in args.fonts:
        print(path)
        for size in range(low, high + 1):
            width, percent = stems(path, size)
            if percent >= args.min:
                print(f"  {size:3} px: {width} px stems, {percent}% even")


if __name__ == "__main__":
    main()
