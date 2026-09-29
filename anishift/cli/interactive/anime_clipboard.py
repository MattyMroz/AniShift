"""Windows clipboard boundary for explicit Anime text-copy actions."""

from __future__ import annotations

import codecs
import shutil
import subprocess

from anishift.utils.logger import get_logger

logger = get_logger(__name__)


def copy_text(value: str) -> bool:
    """Copy Unicode through clip.exe without placing the text in process arguments."""
    executable: str | None = shutil.which("clip.exe")
    if executable is None:
        return False
    try:
        subprocess.run(  # noqa: S603
            [executable],
            input=codecs.BOM_UTF16_LE + value.encode("utf-16-le"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as error:
        logger.warning("Anime clipboard copy failed", error_class=type(error).__name__)
        return False
    return True
