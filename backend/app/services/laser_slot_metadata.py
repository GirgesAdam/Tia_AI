from __future__ import annotations

from dataclasses import dataclass

_MARKER = "||TIA_LASER_DEVICE||"
_SEPARATOR = "||"


@dataclass(frozen=True)
class LaserSlotMetadata:
    branch_name: str | None
    device_key: str | None
    device_name: str | None


def encode_laser_slot_branch(
    branch_name: str | None,
    *,
    device_key: str | None,
    device_name: str | None,
) -> str | None:
    """Carry device identity through an older composite slot snapshot.

    The composite mapper already keeps ``branch_name`` but removes it before any
    customer-language composition. Until that mapper grows first-class device
    fields, this workspace-internal envelope preserves the selected physical
    resource without parsing customer text or leaking it to the customer.
    """
    if not device_key:
        return branch_name
    clean_branch = str(branch_name or "").replace(_MARKER, " ").strip()
    clean_name = str(device_name or "").replace(_SEPARATOR, " ").strip()
    return f"{clean_branch}{_MARKER}{device_key}{_SEPARATOR}{clean_name}"


def decode_laser_slot_branch(value: object) -> LaserSlotMetadata:
    raw = str(value or "")
    if _MARKER not in raw:
        return LaserSlotMetadata(branch_name=raw or None, device_key=None, device_name=None)
    branch_name, payload = raw.split(_MARKER, 1)
    device_key, separator, device_name = payload.partition(_SEPARATOR)
    return LaserSlotMetadata(
        branch_name=branch_name.strip() or None,
        device_key=device_key.strip() or None,
        device_name=(device_name.strip() or None) if separator else None,
    )
