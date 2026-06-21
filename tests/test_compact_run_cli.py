from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def test_compact_run_cli_prints_route_confidence_and_savings(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "examples" / "runs" / "login_error"
    run_copy = tmp_path / "login_error"
    shutil.copytree(fixture, run_copy)

    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "compact_run.py"), str(run_copy)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "step 1: text_only, " in result.stdout
    assert "% saved, confidence 0." in result.stdout
    assert "Email is required" in result.stdout
    assert "total: 1 step(s), " in result.stdout
    assert "compact tokens vs" in result.stdout
