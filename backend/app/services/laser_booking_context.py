from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_selected_laser_device: ContextVar[str | None] = ContextVar(
    "tia_selected_laser_device", default=None
)


def current_laser_device_key() -> str | None:
    return _selected_laser_device.get()


@contextmanager
def laser_device_context(device_key: str | None) -> Iterator[None]:
    token = _selected_laser_device.set(device_key or None)
    try:
        yield
    finally:
        _selected_laser_device.reset(token)
