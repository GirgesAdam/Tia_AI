from __future__ import annotations

from pathlib import Path


path = Path(".github/implementation/group_aware_visit_patch.py")
text = path.read_text(encoding="utf-8")
old = '    "def _read_customer_profile(\\n",\n'
new = '    "def _read_customer_profile",\n'
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one customer-profile marker, found {count}")
path.write_text(text.replace(old, new), encoding="utf-8")
