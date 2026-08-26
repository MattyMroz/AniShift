from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Final

_PROBE_TIMEOUT: Final[int] = 300

_FORBIDDEN_PREFIXES: Final[tuple[str, ...]] = ("anishift.services.llm.engines.palantir",)

_PROBE: Final[str] = """
import json
import sys

import anishift.config.settings  # noqa: F401

prefixes = tuple(json.loads(sys.argv[1]))
offenders = sorted(name for name in sys.modules if name.startswith(prefixes))
print(json.dumps(offenders))
"""


def test_the_settings_module_does_not_pull_the_palantir_engine_package() -> None:
    environment: dict[str, str] = {
        name: value for name, value in os.environ.items() if not name.startswith("ANISHIFT_")
    }
    probe: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _PROBE, json.dumps(_FORBIDDEN_PREFIXES)],
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT,
        check=False,
        env=environment,
    )

    assert probe.returncode == 0, probe.stderr
    loaded: list[str] = json.loads(probe.stdout)
    assert loaded == []
