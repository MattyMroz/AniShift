"""Tests for rich_console.console module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ..console import (
    _has_rich_markup,
    _highlight_outside_rich_markup,
    _patched_console_print,
    auto_highlight_text,
    normalize_numbers,
)

# ── normalize_numbers ─────────────────────────────────────────────────────────


class TestNormalizeNumbers:
    """Test comma-to-dot decimal normalization."""

    def test_comma_to_dot(self):
        assert normalize_numbers("1,5") == "1.5"

    def test_multiple_commas(self):
        assert normalize_numbers("1,5 and 2,3") == "1.5 and 2.3"

    def test_no_numbers(self):
        assert normalize_numbers("hello world") == "hello world"

    def test_already_dot(self):
        assert normalize_numbers("1.5") == "1.5"

    def test_comma_not_between_digits(self):
        assert normalize_numbers("a,b") == "a,b"

    def test_empty_string(self):
        assert normalize_numbers("") == ""

    def test_mixed(self):
        assert normalize_numbers("values: 1,5 and 2.3") == "values: 1.5 and 2.3"


# ── _has_rich_markup ──────────────────────────────────────────────────────────


class TestHasRichMarkup:
    """Test Rich markup detection."""

    def test_plain_text(self):
        assert _has_rich_markup("hello world") is False

    def test_known_prefix_bold(self):
        assert _has_rich_markup("[bold]text[/bold]") is True

    def test_known_prefix_closing(self):
        assert _has_rich_markup("[/bold]") is True

    def test_known_prefix_color(self):
        assert _has_rich_markup("[red]text here[/red]") is True

    def test_known_prefix_color_variant(self):
        assert _has_rich_markup("[red_bold]text[/red_bold]") is True

    def test_false_positive_redis_rejected(self):
        assert _has_rich_markup("[redis_connection]") is False

    def test_false_positive_blacklist_rejected(self):
        assert _has_rich_markup("[blacklist]") is False

    def test_false_positive_redirect_rejected(self):
        assert _has_rich_markup("[redirect]") is False

    def test_known_prefix_repr(self):
        assert _has_rich_markup("[repr.number]42[/repr.number]") is True

    def test_generic_tag_pair(self):
        assert _has_rich_markup("[custom_style]text[/custom_style]") is True

    def test_unmatched_brackets(self):
        assert _has_rich_markup("[not a tag") is False

    def test_empty_string(self):
        assert _has_rich_markup("") is False


# ── auto_highlight_text ───────────────────────────────────────────────────────


class TestAutoHighlightText:
    """Test auto-highlighting of text patterns."""

    def test_plain_text_unchanged(self):
        result = auto_highlight_text("hello")
        assert "hello" in result

    def test_number_highlighted(self):
        result = auto_highlight_text("value 123")
        assert "[repr.number]123[/repr.number]" in result

    def test_float_highlighted(self):
        result = auto_highlight_text("pi is 3.14")
        assert "[repr.number]3.14[/repr.number]" in result

    def test_url_highlighted_blue(self):
        result = auto_highlight_text("visit https://example.com")
        assert "[repr.url]https://example.com[/repr.url]" in result

    def test_true_highlighted(self):
        result = auto_highlight_text("value is True")
        assert "[repr.bool_true]True[/repr.bool_true]" in result

    def test_false_highlighted(self):
        result = auto_highlight_text("value is False")
        assert "[repr.bool_false]False[/repr.bool_false]" in result

    def test_none_highlighted(self):
        result = auto_highlight_text("value is None")
        assert "[repr.none]None[/repr.none]" in result

    def test_already_marked_text_returned_as_is(self):
        text = "[bold]already marked[/bold]"
        result = auto_highlight_text(text)
        assert result == text

    def test_empty_string(self):
        result = auto_highlight_text("")
        assert result == ""

    # ── Paths ─────────────────────────────────────────────────────────────────

    def test_absolute_path(self):
        result = auto_highlight_text("Loading /home/user/.cache/models/v2.1.0")
        assert "[repr.path]/home/user/.cache/models/v2.1.0[/repr.path]" in result

    def test_relative_path_3_segments(self):
        result = auto_highlight_text("saved to output/volume_01/chapter_03/")
        assert "[repr.path]output/volume_01/chapter_03/[/repr.path]" in result

    def test_relative_path_with_extension(self):
        result = auto_highlight_text("Processing: volume_01/chapter_01.cbz")
        assert "[repr.path]volume_01/chapter_01.cbz[/repr.path]" in result

    def test_relative_path_with_long_extension(self):
        result = auto_highlight_text("hashing vae/flux2-vae.safetensors")
        assert "[repr.path]vae/flux2-vae.safetensors[/repr.path]" in result

    def test_path_does_not_match_fraction(self):
        result = auto_highlight_text("24/24 pages")
        assert "[repr.path]" not in result
        assert "[repr.number]24/24[/repr.number]" in result

    # ── Versions ──────────────────────────────────────────────────────────────

    def test_version_v_prefixed(self):
        result = auto_highlight_text("AniShift v2.1.0 starting")
        assert "[repr.number]v2.1.0[/repr.number]" in result

    def test_version_dotted_3_segments(self):
        result = auto_highlight_text("Python 3.13.11")
        assert "[repr.number]3.13.11[/repr.number]" in result

    def test_version_with_build_metadata(self):
        result = auto_highlight_text("torch 2.6.0+cu128")
        assert "[repr.number]2.6.0+cu128[/repr.number]" in result

    # ── Number + unit ─────────────────────────────────────────────────────────

    def test_number_unit_seconds(self):
        result = auto_highlight_text("loaded in 1.33s")
        assert "[repr.number]1.33s[/repr.number]" in result

    def test_number_unit_with_space(self):
        result = auto_highlight_text("size is 8.04 GB")
        assert "[repr.number]8.04 GB[/repr.number]" in result

    def test_number_unit_megabytes(self):
        result = auto_highlight_text("file size 245MB")
        assert "[repr.number]245MB[/repr.number]" in result

    def test_number_unit_milliseconds(self):
        result = auto_highlight_text("latency 42ms")
        assert "[repr.number]42ms[/repr.number]" in result

    # ── Fractions ─────────────────────────────────────────────────────────────

    def test_fraction(self):
        result = auto_highlight_text("Batch 3/5 done")
        assert "[repr.number]3/5[/repr.number]" in result

    def test_fraction_larger(self):
        result = auto_highlight_text("Detection 156/156 regions")
        assert "[repr.number]156/156[/repr.number]" in result

    # ── Punctuation NOT colored ───────────────────────────────────────────────

    def test_colon_not_colored(self):
        result = auto_highlight_text("key: value")
        assert "[special]" not in result

    def test_comma_not_colored(self):
        result = auto_highlight_text("24 files, 12MB")
        assert "files," in result  # comma stays as-is

    def test_parens_not_colored(self):
        result = auto_highlight_text("(avg 27ms/region)")
        assert "\\[" not in result or "(" in result  # parens stay literal

    def test_em_dash_not_colored(self):
        result = auto_highlight_text("loaded — 3 profiles")
        assert "[special]" not in result

    # ── Bracket escaping ──────────────────────────────────────────────────────

    def test_literal_bracket_escaped(self):
        result = auto_highlight_text("result[0] = 42")
        assert "\\[" in result
        assert "[repr.number]0[/repr.number]" in result
        assert "[repr.number]42[/repr.number]" in result

    def test_literal_brackets_no_crash_from_markup(self):
        """Escaped brackets should render without errors in Rich."""
        from rich.text import Text

        result = auto_highlight_text("array[1:3]")
        # Should not raise
        Text.from_markup(result)

    @pytest.mark.parametrize(
        "text",
        [
            "[repr.number]42[/repr.number]",
            "[bold]text[/bold]",
            "[info]msg[/info]",
        ],
    )
    def test_existing_markup_not_double_highlighted(self, text):
        result = auto_highlight_text(text)
        assert result == text


# ── _highlight_outside_rich_markup ────────────────────────────────────────────


class TestHighlightOutsideRichMarkup:
    """Test selective highlighting around existing markup."""

    def test_plain_text_highlighted(self):
        result = _highlight_outside_rich_markup("value 42")
        assert "[repr.number]42[/repr.number]" in result

    def test_preserves_existing_markup(self):
        text = "[bold]hello[/bold] world 42"
        result = _highlight_outside_rich_markup(text)
        assert "[bold]hello[/bold]" in result
        assert "[repr.number]42[/repr.number]" in result

    def test_only_markup_returned_as_is(self):
        text = "[bold]test[/bold]"
        result = _highlight_outside_rich_markup(text)
        assert "[bold]test[/bold]" in result

    def test_empty_string(self):
        assert _highlight_outside_rich_markup("") == ""

    def test_no_double_highlight(self):
        text = "[repr.number]42[/repr.number]"
        result = _highlight_outside_rich_markup(text)
        assert result.count("[repr.number]") == 1

    def test_container_markup_highlights_inner_numbers(self):
        text = "[dim]Hashing text_encoders/qwen-3-4b.safetensors (8.04 GB)…[/dim]"
        result = _highlight_outside_rich_markup(text)

        assert "[dim]" in result
        assert "[/dim]" in result
        assert "[repr.number]8.04 GB[/repr.number]" in result


# ── _patched_console_print ────────────────────────────────────────────────────


class TestPatchedConsolePrint:
    """Test monkey-patched console.print branches."""

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_plain_text_auto_highlighted(self, mock_print: MagicMock):
        _patched_console_print("value 42")
        mock_print.assert_called_once()
        arg = mock_print.call_args[0][0]
        assert "[repr.number]42[/repr.number]" in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_markup_text_highlights_unstyled_tail(self, mock_print: MagicMock):
        _patched_console_print("[bold]hello[/bold]")
        arg = mock_print.call_args[0][0]
        assert "[bold]hello[/bold]" in arg

        _patched_console_print("[green]done[/green] (0.0s)")
        arg = mock_print.call_args[0][0]
        assert "[green]done[/green]" in arg
        assert "[repr.number]0.0s[/repr.number]" in arg

        _patched_console_print("[dim]Hashing text_encoders/qwen-3-4b.safetensors (8.04 GB)…[/dim]")
        arg = mock_print.call_args[0][0]
        assert "[repr.number]8.04 GB[/repr.number]" in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_explicit_highlight_true_with_markup(self, mock_print: MagicMock):
        _patched_console_print("[bold]hi[/bold] 42", highlight=True)
        arg = mock_print.call_args[0][0]
        assert "[bold]hi[/bold]" in arg
        assert "[repr.number]42[/repr.number]" in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_explicit_highlight_true_plain(self, mock_print: MagicMock):
        _patched_console_print("value 99", highlight=True)
        arg = mock_print.call_args[0][0]
        assert "[repr.number]99[/repr.number]" in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_highlight_false_no_highlighting(self, mock_print: MagicMock):
        _patched_console_print("value 42", highlight=False)
        arg = mock_print.call_args[0][0]
        assert "[repr.number]" not in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_bracket_escaping(self, mock_print: MagicMock):
        _patched_console_print("config [section]", highlight=False)
        arg = mock_print.call_args[0][0]
        assert "\\[section]" in arg

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_non_string_passthrough(self, mock_print: MagicMock):
        obj = {"key": "value"}
        _patched_console_print(obj)
        mock_print.assert_called_once()
        assert mock_print.call_args[0][0] is obj

    @patch("anishift.utils.rich_console.console._original_console_print")
    def test_comma_normalization(self, mock_print: MagicMock):
        _patched_console_print("value 1,5", highlight=False)
        arg = mock_print.call_args[0][0]
        assert "1.5" in arg
