from __future__ import annotations

from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests/test_realtime_recovery.py"
text = path.read_text(encoding="utf-8")
old = '    assert "مدينة نصر" in reply\n'
new = '    assert "مدينة نصر" not in reply\n'
count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected one stale branch assertion, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Single-location test contract updated.")
