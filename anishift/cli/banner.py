"""Startup banner — the top canvas of the interactive shell.

The ASCII-art is isolated in :data:`_LOGO` so it can be swapped without
touching the layout or status line.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from anishift.bootstrap import AppContext
from utils.rich_console import console

__all__ = ["show_banner"]

# ── Constants ──────────────────────────────────────────────────────────────

_LOGO: str = r"""
 █████╗ ███╗   ██╗██╗███████╗██╗  ██╗██╗███████╗████████╗
██╔══██╗████╗  ██║██║██╔════╝██║  ██║██║██╔════╝╚══██╔══╝
███████║██╔██╗ ██║██║███████╗███████║██║█████╗     ██║
██╔══██║██║╚██╗██║██║╚════██║██╔══██║██║██╔══╝     ██║
██║  ██║██║ ╚████║██║███████║██║  ██║██║██║        ██║
╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝
"""
"""ASCII-art logo drawn on shell start (swap freely — nothing else depends on it)."""


def _package_version() -> str:
    """Return the installed package version, or ``"dev"`` when not installed."""
    try:
        return version("anishift")
    except PackageNotFoundError:
        return "dev"


def show_banner(context: AppContext) -> None:
    """Render the startup logo and a one-line status.

    Args:
        context: Wired context; its ``user_settings.mode`` drives the status.
    """
    console.print(f"[ruby_red_bold]{_LOGO}[/ruby_red_bold]")
    console.print(
        f"[gray]terminal-based anime lector for Polish · "
        f"v{_package_version()} · mode: [/gray][info]{context.user_settings.mode}[/info]"
    )
