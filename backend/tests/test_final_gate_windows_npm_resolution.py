from pathlib import Path


def test_final_gate_resolves_windows_npm_cmd_before_subprocess() -> None:
    backend = Path(__file__).resolve().parent.parent
    source = (backend / "scripts/run_final_internal_gate.py").read_text(encoding="utf-8")

    assert 'shutil.which("npm.cmd")' in source
    assert 'shutil.which("npm")' in source
    assert '["npm","run","test:e2e"]' not in source
    assert "npm executable not found in PATH" in source
