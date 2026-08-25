"""Generic MATLAB call builder - used for NORDIC denoising (denoise.py) and
the SANDI-Matlab-Toolbox (sandi.py). Requires MATLAB, NORDIC
(https://github.com/SteenMoeller/NORDIC_Raw), and the SANDI toolbox
(https://github.com/palombom/SANDI-Matlab-Toolbox-Latest-Release) installed
separately.
"""

from __future__ import annotations


def add_path(directory: str) -> str:
    return f"addpath('{directory}')"


def add_path_recursive(directory: str) -> str:
    return f"addpath(genpath('{directory}'))"


def matlab_command(expression: str, statements_before: list[str] | None = None) -> list[str]:
    """Build a `matlab -nodisplay -nosplash -r "..."` call.
    `statements_before` are raw MATLAB statements (e.g. from `add_path`/
    `add_path_recursive`) run before `expression`.

    `expression` runs inside try/catch with an explicit `exit(1)` on error
    - MATLAB's `-r` does NOT set a nonzero process exit code for an
    uncaught error by default, so without this, external/run.py's
    exit-code check can't actually detect a failed MATLAB call (found by
    a real silent failure: a MATLAB error left an external tool call
    reporting success)."""
    setup = "".join(f"{s}; " for s in (statements_before or []))
    full_expr = f"{setup}try; {expression}; catch ME; disp(getReport(ME)); exit(1); end; exit(0);"
    return ["matlab", "-nodisplay", "-nosplash", "-nodesktop", "-r", full_expr]
