"""Rich console wrapper with custom theme, utilities and progress bars.

Provide a preconfigured Rich Console with:
- Custom theme (150+ styles)
- Auto-highlighting (URLs, paths, booleans, versions, numbers+units, fractions)
- Progress bars with dynamic color transitions
- Utility functions (status icons, byte/time formatting)

Public API:
    console: Preconfigured Console instance with auto-highlighting
    RICH_THEME: Complete theme definition (150+ styles)
    Colors: Color constants for programmatic use
    ProgressBarManager: Modular progress bar with dynamic colors
    StatusType: Literal type for supported status icon names
    Utilities: get_status_icon, format_bytes, format_duration, format_percentage, get_progress_color

Usage:
    >>> from rich_console import console
    >>> console.print("Processing 100 files")  # Auto-highlights numbers

    >>> from rich_console import ProgressBarManager
    >>> with ProgressBarManager("Downloading", total=100) as pb:
    ...     pb.advance(50)

    >>> from rich_console import format_bytes, format_duration
    >>> print(format_bytes(1024**3))  # "1.07 GB"
    >>> print(format_duration(3665))  # "1h 1m 5.00s"
"""

from __future__ import annotations

from .console import console
from .progress import (
    ProgressBarBuilder,
    ProgressBarManager,
)
from .theme import RICH_THEME, Colors
from .utilities import (
    StatusType,
    format_bytes,
    format_duration,
    format_percentage,
    get_progress_color,
    get_status_icon,
)

__all__ = [
    "RICH_THEME",
    "Colors",
    "ProgressBarBuilder",
    "ProgressBarManager",
    "StatusType",
    "console",
    "format_bytes",
    "format_duration",
    "format_percentage",
    "get_progress_color",
    "get_status_icon",
]

__version__ = "1.0.0"
