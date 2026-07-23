"""Build-time step: pre-decompress Data/TimelessJewelData/*.zip[.partN] into
.bin siblings using a real zlib (this runs in the Docker build's Python
stage, not inside headless Lua).

Headless PoB's own Inflate() is a stubbed no-op (HeadlessWrapper.lua) -- the
same constraint already documented for PoB share-code compression
(app/pob/decode.py handles that one in Python instead). Timeless Jewel data
hits the identical wall: DataLegionLookUpTableHelper.lua::loadJewelFile()
calls Inflate() on the .zip bytes to build the .bin cache the first time,
which silently produces nothing in headless mode -- any build socketing a
Timeless Jewel (Lethal Pride, Glorious Vanity, ...) then fails to load
properly and PoB falls back to a blank/default build (wrong class,
ascendancy, and every stat) instead of erroring.

loadJewelFile() already prefers an up-to-date .bin file over decompressing
the .zip itself when one exists, so generating .bin files here -- with a
real zlib -- lets that existing fast path just work, without needing a real
Inflate() in Lua at all.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "vendor" / "PathOfBuilding" / "src" / "Data" / "TimelessJewelData"


def main() -> None:
    if not DATA_DIR.is_dir():
        raise SystemExit(f"TimelessJewelData dir not found: {DATA_DIR}")

    # Plain "<name>.zip" files.
    for zip_path in sorted(DATA_DIR.glob("*.zip")):
        _write_bin(zip_path.with_suffix(""), zip_path.read_bytes())

    # Split "<name>.zip.part0", ".part1", ... groups -- concatenate in
    # numeric part order before decompressing (mirrors the Lua loader's
    # own t_concat(splitFile, "") over NewFileSearch's match order).
    part_groups: dict[str, list[Path]] = {}
    for part_path in DATA_DIR.glob("*.zip.part*"):
        m = re.match(r"^(.*\.zip)\.part(\d+)$", part_path.name)
        if not m:
            continue
        part_groups.setdefault(m.group(1), []).append(part_path)

    for zip_name, parts in part_groups.items():
        parts.sort(key=lambda p: int(re.search(r"\.part(\d+)$", p.name).group(1)))
        combined = b"".join(p.read_bytes() for p in parts)
        _write_bin(DATA_DIR / zip_name[: -len(".zip")], combined)


def _write_bin(base_path: Path, compressed: bytes) -> None:
    bin_path = base_path.with_suffix(".bin")
    data = zlib.decompress(compressed)
    bin_path.write_bytes(data)
    print(f"{bin_path.name}: {len(compressed)} -> {len(data)} bytes")


if __name__ == "__main__":
    main()
