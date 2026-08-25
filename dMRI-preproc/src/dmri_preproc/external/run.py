"""Direct subprocess execution for every external tool call (FSL, MRtrix,
MATLAB/NORDIC, the SANDI toolbox).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(cmd: list[str], step_name: str, log_dir: str | Path | None = None) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{step_name}.stdout.log").write_text(proc.stdout)
        (log_dir / f"{step_name}.stderr.log").write_text(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{step_name} failed (exit {proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
        )
