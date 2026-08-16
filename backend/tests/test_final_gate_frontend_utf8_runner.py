from pathlib import Path


def test_frontend_process_capture_is_explicit_utf8_with_replacement() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "scripts" / "run_final_internal_gate.py"
    ).read_text(encoding="utf-8")

    assert 'encoding="utf-8"' in source
    assert 'errors="replace"' in source
    assert "run_captured_process(" in source
    assert "(proc.stdout or \"\")[-8000:]" in source
    assert "(proc.stderr or \"\")[-8000:]" in source


def test_focused_frontend_runner_does_not_reset_full_staging_suite() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (
        backend / "scripts" / "run_frontend_e2e_gate.py"
    ).read_text(encoding="utf-8")

    assert "seed_final_internal_gate.py" in source
    assert "validate_final_gate_fixture_quality.py" in source
    assert "seed_full_staging_demo.py" not in source
    assert '[npm_executable, "run", "test:e2e"]' in source


def test_utf8_child_output_round_trip_does_not_use_local_charmap(tmp_path) -> None:
    import subprocess
    import sys

    code = (
        "import sys;"
        "sys.stdout.buffer.write('هند مصطفى — اختبار ✓'.encode('utf-8'))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout == "هند مصطفى — اختبار ✓"
    assert proc.stderr == ""
