from __future__ import annotations

import os
import subprocess
import sys
import traceback

print("TIA_AGENT_EVAL_DIAGNOSTIC_START", flush=True)
print(f"python={sys.version.split()[0]}", flush=True)
print(f"cwd={os.getcwd()}", flush=True)
print(f"pythonpath={os.getenv('PYTHONPATH', '')}", flush=True)

try:
    from app.core.config import settings
    print(
        "config_ok "
        f"environment={settings.environment} "
        f"model={settings.openai_model} "
        f"database_scheme_ok={settings.database_url.startswith('postgresql+psycopg://')}",
        flush=True,
    )
except Exception as exc:
    print(f"config_error={type(exc).__name__}: {exc}", flush=True)
    traceback.print_exc()
    raise SystemExit(91) from exc

try:
    import tools.agent_eval.run_batch_01  # noqa: F401
    print("eval_import_ok", flush=True)
except Exception as exc:
    print(f"eval_import_error={type(exc).__name__}: {exc}", flush=True)
    traceback.print_exc()
    raise SystemExit(92) from exc

command = [
    sys.executable,
    "-u",
    "-m",
    "tools.agent_eval.run_batch_01",
    "--workspace-slug",
    "tia",
    "--output-dir",
    "/app/backend/eval_results",
    "--git-sha",
    os.getenv("TIA_AGENT_EVAL_GIT_SHA", "unknown"),
]
print("eval_exec_start", flush=True)
completed = subprocess.run(command, check=False)
print(f"eval_exec_exit={completed.returncode}", flush=True)
raise SystemExit(completed.returncode)
