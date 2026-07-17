"""Progress bar system with dynamic color transitions.

Features:
- Modular show/hide flags for all components
- Dynamic color transitions (any number of colors)
- Multiple bar styles (rich, blocks, custom)
- Download mode with bytes + speed
- Context manager interface

Usage:
    >>> from rich_console.progress import ProgressBarManager
    >>> with ProgressBarManager("Processing", total=100) as pb:
    ...     pb.advance(50)

    >>> # Download mode
    >>> with ProgressBarManager("file.zip", total=100_000_000,
    ...     show_download=True, show_speed=True) as pb:
    ...     pb.advance(10_000_000)
"""

from __future__ import annotations

from .manager import ProgressBarBuilder, ProgressBarManager
from .multi import MultiProgressManager

__all__ = ["MultiProgressManager", "ProgressBarBuilder", "ProgressBarManager"]
