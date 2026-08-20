from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
REQUIRED_SIZES = {size[0] for size in SIZES}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def fail(message: str) -> None:
    raise SystemExit(f"Windows icon preparation failed: {message}")


def load_largest_frame(source: Path) -> Image.Image:
    with Image.open(source) as icon:
        available = icon.info.get("sizes") or {(icon.width, icon.height)}
        largest = max(available, key=lambda size: size[0] * size[1])
        if hasattr(icon, "ico"):
            frame = icon.ico.getimage(largest)
        else:
            frame = icon.copy()
        return frame.convert("RGBA")


def validate_bmp_backed_ico(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 6:
        fail(f"{path} is too small to be a valid ICO file")

    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        fail(f"{path} has an invalid ICO header")

    directory_end = 6 + count * 16
    if directory_end > len(data):
        fail(f"{path} has a truncated icon directory")

    found: set[int] = set()
    for index in range(count):
        entry_offset = 6 + index * 16
        width_raw, height_raw, _, _, planes, bit_count, byte_count, image_offset = struct.unpack_from(
            "<BBBBHHII", data, entry_offset
        )
        width = width_raw or 256
        height = height_raw or 256

        if width != height:
            fail(f"frame {index + 1} is not square ({width}x{height})")
        if image_offset < directory_end or image_offset + byte_count > len(data):
            fail(f"frame {index + 1} points outside the ICO file")

        image_data = data[image_offset : image_offset + byte_count]
        if image_data.startswith(PNG_SIGNATURE):
            fail(f"frame {width}x{height} is still PNG-compressed")
        if len(image_data) < 40 or struct.unpack_from("<I", image_data, 0)[0] < 40:
            fail(f"frame {width}x{height} does not contain a valid BMP/DIB header")
        if planes not in (0, 1) or bit_count not in (24, 32):
            fail(f"frame {width}x{height} has unsupported ICO metadata")

        found.add(width)

    missing = sorted(REQUIRED_SIZES - found)
    if missing:
        fail(f"missing icon sizes: {', '.join(map(str, missing))} px")


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: prepare-windows-icon.py SOURCE.ico OUTPUT.ico")

    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if not source.is_file():
        fail(f"source icon not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    image = load_largest_frame(source)
    image.save(output, format="ICO", sizes=SIZES, bitmap_format="bmp")
    validate_bmp_backed_ico(output)

    print(
        f"Prepared Windows icon: {output} "
        "(16, 24, 32, 48, 64, 128, 256 px; BMP/DIB-backed frames)"
    )


if __name__ == "__main__":
    main()
