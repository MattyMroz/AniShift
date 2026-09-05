"""Setup layer — diagnostics (doctor) and binary installation."""

from __future__ import annotations

from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor

__all__ = [
    "CheckResult",
    "CheckStatus",
    "run_doctor",
]
