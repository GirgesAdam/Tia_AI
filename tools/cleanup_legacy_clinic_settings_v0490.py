from __future__ import annotations

from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "DELETIONS_v0.49.0.txt"
    if not manifest.exists():
        print("Missing DELETIONS_v0.49.0.txt", file=sys.stderr)
        return 2
    removed = 0
    missing = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        target = root / item
        try:
            target.relative_to(root)
        except ValueError:
            print(f"Refusing path outside project: {item}", file=sys.stderr)
            return 3
        if target.is_file() or target.is_symlink():
            target.unlink()
            removed += 1
            print(f"removed  {item}")
        elif target.exists() and target.is_dir():
            print(f"refusing directory deletion: {item}", file=sys.stderr)
            return 4
        else:
            missing += 1
    for cache in root.rglob("__pycache__"):
        if cache.is_dir():
            for child in cache.iterdir():
                if child.is_file() and child.suffix == ".pyc":
                    child.unlink(missing_ok=True)
            try:
                cache.rmdir()
            except OSError:
                pass
    print(f"cleanup complete: {removed} removed, {missing} already absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
