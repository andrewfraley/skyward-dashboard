"""Render the e-paper layout on this computer, as PNGs, without flashing a display.

Builds display/esphome/tests/preview.yaml for ESPHome's host platform (the real
layout lambda, with a display driver that writes files), runs it against a
dashboard's /api/display, and converts what it drew to PNG:

    uv run python scripts/display_preview.py                 # the demo dashboard on :8087
    uv run python scripts/display_preview.py --url http://127.0.0.1:8087

Needs g++ and the ESPHome venv (esphome-venv/, or --esphome). Serve the demo data
first (see DEVELOPING.md), never your own: the PNGs land in recordings/, which is
gitignored, but they're pictures of whatever the dashboard shows.
"""

import argparse
import json
import struct
import subprocess
import sys
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "display" / "esphome" / "tests" / "preview.yaml"
OUT = ROOT / "recordings" / "display-preview"


def pbm_to_png(pbm: Path, png: Path) -> None:
    """Binary PBM (P4, 1 = black) to a 1-bit greyscale PNG (1 = white)."""
    data = pbm.read_bytes()
    header, _, rest = data.partition(b"\n")
    size, _, pixels = rest.partition(b"\n")
    if header != b"P4":
        raise ValueError(f"{pbm} is not a binary PBM")
    width, height = map(int, size.split())
    row = (width + 7) // 8
    raw = b"".join(
        b"\0" + bytes(~b & 0xFF for b in pixels[y * row : (y + 1) * row]) for y in range(height)
    )

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8087", help="the dashboard to render")
    parser.add_argument("--out", type=Path, default=OUT, help="where the PNGs go")
    parser.add_argument("--esphome", default=str(ROOT / "esphome-venv" / "bin" / "esphome"))
    parser.add_argument(
        "--any-data",
        action="store_true",
        help="render a dashboard whose students aren't the demo one (never for docs)",
    )
    args = parser.parse_args()

    # Pictures of real grades are easy to share by mistake: demo data only, by default.
    with urllib.request.urlopen(f"{args.url}/api/display?v=1", timeout=10) as r:
        names = {s["name"] for s in json.load(r)["students"]}
    if names - {"Demo"} and not args.any_data:
        print(
            "Refusing: the dashboard has students other than the demo one. Serve the demo "
            "data (DEVELOPING.md), or pass --any-data for a private look.",
            file=sys.stderr,
        )
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.p?m"):
        old.unlink()
    subs = ["-s", "dashboard_url", args.url, "-s", "out_dir", str(args.out.resolve())]
    # `run` builds for the host and runs the program, which exits once it has drawn.
    result = subprocess.run(
        [args.esphome, *subs, "run", str(CONFIG), "--no-logs"], cwd=CONFIG.parent
    )
    pbms = sorted(args.out.glob("*.pbm"))
    if not pbms:
        print("Nothing was drawn; see the output above.", file=sys.stderr)
        return result.returncode or 1
    for pbm in pbms:
        pbm_to_png(pbm, pbm.with_suffix(".png"))
        pbm.unlink()
        print(pbm.with_suffix(".png").relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
