"""Setup layer — diagnostics (doctor) and binary installation.

``doctor`` symbols are re-exported here; ``installer`` is imported directly
as ``anishift.setup.installer``.
"""

from __future__ import annotations

from anishift.setup.doctor import CheckResult, CheckStatus, run_doctor

__all__ = [
    "CheckResult",
    "CheckStatus",
    "run_doctor",
]
