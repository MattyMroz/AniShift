"""Validated configuration and host resolution for SAPI."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import TtsConfigError, TtsUnsupportedError, TtsVoiceError
from anishift.services.tts.types import ProcessArchitecture

from .constants import SAPI_PROFILES, SAPI_RATE_MAX, SAPI_RATE_MIN
from .types import SapiHost, SapiVoiceProfile

__all__ = [
    "SapiConfig",
    "resolve_host",
    "resolve_voice_profile",
    "sapi_rate",
    "sapi_volume",
]


@dataclass(frozen=True, slots=True)
class SapiConfig:
    """Resolved engine settings for one architecture-specific worker."""

    provider_model_id: str
    profile: SapiVoiceProfile
    hosts: tuple[SapiHost, ...]
    host: SapiHost | None
    worker_asset: Path
    native_rate: int | float
    native_volume: int | float
    request_timeout_s: float
    shutdown_deadline_s: float
    platform_supported: bool

    @classmethod
    def from_tts_config(
        cls,
        config: TtsConfig,
        *,
        platform_name: str | None = None,
        windows_dir: Path | None = None,
        worker_asset: Path | None = None,
    ) -> SapiConfig:
        """Resolve a shared TTS config without starting COM or a subprocess."""
        if config.max_concurrency != 1:
            _raise_config_error("SAPI max concurrency must be exactly 1", field_name="max_concurrency")
        if config.native_pitch is not None or config.engine_options:
            _raise_unsupported("SAPI does not accept pitch or provider-specific options")
        profile: SapiVoiceProfile = resolve_voice_profile(config.voice_id)
        raw_rate: str | int | float = (
            config.native_rate if config.native_rate is not None else profile.default_native_rate
        )
        raw_volume: str | int | float = (
            config.native_volume if config.native_volume is not None else profile.default_native_volume
        )
        if isinstance(raw_rate, bool) or not isinstance(raw_rate, (int, float)):
            _raise_unsupported("SAPI native rate must be numeric")
        if isinstance(raw_volume, bool) or not isinstance(raw_volume, (int, float)):
            _raise_unsupported("SAPI native volume must be numeric")
        native_rate: int | float = raw_rate
        native_volume: int | float = raw_volume
        _validate_native_settings(profile, native_rate=native_rate, native_volume=native_volume)
        current_platform: str = platform_name or sys.platform
        supported: bool = current_platform == "win32"
        resolved_windows_dir: Path | None = windows_dir or _windows_dir()
        hosts: tuple[SapiHost, ...] = (
            tuple(
                discovered_host
                for architecture in ProcessArchitecture
                if (discovered_host := resolve_host(architecture, windows_dir=resolved_windows_dir)) is not None
            )
            if supported
            else ()
        )
        host: SapiHost | None = next(
            (candidate for candidate in hosts if candidate.architecture is profile.architecture),
            None,
        )
        asset: Path = worker_asset or Path(__file__).with_name("sapi_worker.ps1")
        return cls(
            provider_model_id=config.provider_model_id,
            profile=profile,
            hosts=hosts,
            host=host,
            worker_asset=asset,
            native_rate=native_rate,
            native_volume=native_volume,
            request_timeout_s=config.request_timeout_s,
            shutdown_deadline_s=config.shutdown_deadline_s,
            platform_supported=supported,
        )

    @property
    def resolved_rate(self) -> int:
        """Return the integer assigned to ``SpVoice.Rate``."""
        return sapi_rate(self.profile, self.native_rate)

    @property
    def resolved_volume(self) -> int:
        """Return the integer assigned to ``SpVoice.Volume``."""
        return sapi_volume(self.profile, self.native_volume)


def resolve_voice_profile(voice_id: str) -> SapiVoiceProfile:
    """Resolve aliases, exact names, and architecture-qualified voice IDs."""
    candidate: str = voice_id.strip()
    if not candidate:
        _raise_voice_error("SAPI voice id cannot be empty")
    alias_match: SapiVoiceProfile | None = SAPI_PROFILES.get(candidate.casefold())
    if alias_match is not None:
        return alias_match
    unqualified, separator, architecture = candidate.rpartition("@")
    name: str = unqualified if separator else candidate
    for profile in SAPI_PROFILES.values():
        if name.casefold() != profile.voice_name.casefold():
            continue
        if separator and architecture.casefold() != profile.architecture.value:
            _raise_voice_error(
                f"SAPI voice {profile.voice_name!r} is not available as {architecture!r}",
            )
        return profile
    return _raise_voice_error(f"Unknown SAPI voice: {voice_id!r}")


def resolve_host(
    architecture: ProcessArchitecture,
    *,
    windows_dir: Path | None,
) -> SapiHost | None:
    """Resolve a PowerShell host without shell expansion or PATH lookup."""
    if windows_dir is None:
        return None
    host_directory: str = "System32" if architecture is ProcessArchitecture.X64 else "SysWOW64"
    executable: Path = windows_dir / host_directory / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        return None
    return SapiHost(architecture=architecture, executable=executable.resolve())


def sapi_rate(profile: SapiVoiceProfile, native_rate: int | float) -> int:
    """Convert the selected user-facing rate to the SAPI integer scale."""
    if not profile.uses_wpm_rate:
        return int(native_rate)
    words_per_minute: float = float(native_rate)
    converted: int = round((words_per_minute - 150.0) / 25.0)
    return max(SAPI_RATE_MIN, min(SAPI_RATE_MAX, converted))


def sapi_volume(profile: SapiVoiceProfile, native_volume: int | float) -> int:
    """Convert the selected user-facing volume to the SAPI integer scale."""
    if profile.uses_fractional_volume:
        return round(float(native_volume) * 100)
    return int(native_volume)


def _windows_dir() -> Path | None:
    raw_windows_dir: str = os.environ.get("WINDIR", "").strip()
    return Path(raw_windows_dir) if raw_windows_dir else None


def _validate_native_settings(
    profile: SapiVoiceProfile,
    *,
    native_rate: int | float,
    native_volume: int | float,
) -> None:
    if isinstance(native_rate, bool) or not isinstance(native_rate, (int, float)):
        _raise_unsupported("SAPI native rate must be numeric")
    if isinstance(native_volume, bool) or not isinstance(native_volume, (int, float)):
        _raise_unsupported("SAPI native volume must be numeric")
    if profile.uses_wpm_rate and native_rate <= 0:
        _raise_unsupported("Zosia rate must be greater than 0 WPM")
    if not profile.uses_wpm_rate and not float(native_rate).is_integer():
        _raise_unsupported("Agnieszka rate must be an integer")
    if not profile.uses_wpm_rate and not SAPI_RATE_MIN <= native_rate <= SAPI_RATE_MAX:
        _raise_unsupported("Agnieszka rate must be between -10 and 10")
    maximum_volume: float = 1.0 if profile.uses_fractional_volume else 100.0
    if not profile.uses_fractional_volume and not float(native_volume).is_integer():
        _raise_unsupported("Agnieszka volume must be an integer")
    if not 0 <= native_volume <= maximum_volume:
        _raise_unsupported(f"SAPI volume must be between 0 and {maximum_volume:g}")


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Use one SAPI worker and a concurrency value of 1.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)


def _raise_voice_error(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_VOICE_INVALID,
        message=message,
        suggestion="Select Zosia x64 or Agnieszka x86.",
    )
    raise TtsVoiceError(context=context)


def _raise_unsupported(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message=message,
        suggestion="Use the native rate and volume scales shown for the selected SAPI voice.",
    )
    raise TtsUnsupportedError(context=context)
