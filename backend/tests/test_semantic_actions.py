from app.agents.semantic_actions import select_slot_from_structured_selection

OUTPUT = {
    "ok": True,
    "slots": [
        {"start_time_24h": "18:00"},
        {"start_time_24h": "18:15"},
    ],
}


def test_structured_index_selects_exact_snapshot_row() -> None:
    assert (
        select_slot_from_structured_selection(
            OUTPUT,
            selection_index=1,
            selection_time=None,
        )
        == OUTPUT["slots"][0]
    )


def test_structured_time_selects_exact_snapshot_row() -> None:
    assert (
        select_slot_from_structured_selection(
            OUTPUT,
            selection_index=None,
            selection_time="18:15",
        )
        == OUTPUT["slots"][1]
    )


def test_missing_selection_does_not_guess() -> None:
    assert (
        select_slot_from_structured_selection(
            OUTPUT,
            selection_index=None,
            selection_time=None,
        )
        is None
    )
