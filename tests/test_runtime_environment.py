import subprocess
import sys
from pathlib import Path


def test_runtime_environment_in_isolated_qt_process(tmp_path):
    # Windows Qt retains process-wide QML/renderer state. Keep these additional
    # engine and thread lifecycle checks independent of the other UI fixtures.
    checks = Path(__file__).with_name("runtime_environment_checks.py")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(checks), "--basetemp", str(tmp_path / "checks")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
