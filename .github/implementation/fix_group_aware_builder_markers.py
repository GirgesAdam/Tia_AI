from __future__ import annotations

from pathlib import Path


path = Path(".github/implementation/group_aware_visit_patch.py")
text = path.read_text(encoding="utf-8")
replacements = (
    (
        '    "def _read_customer_profile(\\n",\n',
        '    "def _read_customer_profile",\n',
        "customer-profile",
    ),
    (
        '    "def _package_filters(\\n",\n',
        '    "def _package_filters",\n',
        "package-filters",
    ),
)
for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one {label} marker, found {count}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
