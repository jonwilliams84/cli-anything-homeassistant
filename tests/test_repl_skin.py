"""Unit tests for cli_anything.homeassistant.utils.repl_skin — the REPL skin.

The skin is pure presentation, but it is user-facing surface: a broken banner,
a prompt that hides the modified marker or a table that crashes on a long cell
are visible defects. These tests exercise every public method plus the
module-level helpers, with colors both ON (a fake stdout that claims isatty)
and OFF, because both paths run in the wild.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cli_anything.homeassistant.utils import repl_skin
from cli_anything.homeassistant.utils.repl_skin import (
    ReplSkin,
    _display_home_path,
    _strip_ansi,
    _visible_len,
)


class FakeTty:
    """A stdout stand-in that claims to be a terminal."""

    def __init__(self):
        self.written: list[str] = []

    def isatty(self):
        return True

    def write(self, text):
        self.written.append(text)


# ────────────────────────────────────────────────────── module-level helpers


class TestHelpers:
    def test_strip_ansi_removes_all_escape_codes(self):
        text = "\033[38;5;80m\033[1m◆\033[0m plain"
        assert _strip_ansi(text) == "◆ plain"

    def test_strip_ansi_on_plain_text_is_identity(self):
        assert _strip_ansi("no codes here") == "no codes here"

    def test_visible_len_ignores_codes(self):
        assert _visible_len("\033[1mbold\033[0m") == 4

    def test_display_home_path_relative_to_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _display_home_path(str(tmp_path / "sub" / "file")).startswith("~/")

    def test_display_home_path_outside_home_is_absolute(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        assert _display_home_path(str(outside)) == str(outside.resolve())


# ──────────────────────────────────────────────────────────────── construction


class TestInit:
    def test_name_normalization(self, tmp_path):
        skin = ReplSkin("Home_Assistant", history_file=str(tmp_path / "h"))
        assert skin.software == "home_assistant"
        assert skin.display_name == "Home Assistant"
        hyphen = ReplSkin("Home-Assistant", history_file=str(tmp_path / "h2"))
        assert hyphen.software == "home_assistant"

    def test_skill_ids_derived_from_software(self, tmp_path):
        skin = ReplSkin("homeassistant", history_file=str(tmp_path / "h"))
        assert skin.skill_id == "cli-anything-homeassistant"
        assert "-g -y" in skin.skill_install_cmd

    def test_alias_maps_iterm2_ctl(self, tmp_path):
        skin = ReplSkin("iterm2_ctl", history_file=str(tmp_path / "h"))
        assert skin.skill_id == "cli-anything-iterm2"

    def test_explicit_skill_path_is_kept(self, tmp_path):
        marker = tmp_path / "SKILL.md"
        marker.write_text("# skill")
        skin = ReplSkin("homeassistant", skill_path=str(marker), history_file=str(tmp_path / "h"))
        assert skin.skill_path == str(marker)

    def test_skill_path_autodetected_from_package(self, tmp_path):
        """No explicit path: falls back to the packaged skills/SKILL.md."""
        skin = ReplSkin("homeassistant", history_file=str(tmp_path / "h"))
        packaged = Path(__file__).resolve().parents[1] / (
            "cli_anything/homeassistant/skills/SKILL.md"
        )
        expected = packaged if packaged.is_file() else skin.skill_path
        if packaged.is_file():
            assert skin.skill_path == str(packaged)

    def test_explicit_history_file_is_used(self, tmp_path):
        hist = tmp_path / "history"
        skin = ReplSkin("homeassistant", history_file=str(hist))
        assert skin.history_file == str(hist)

    def test_default_history_file_lives_under_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        skin = ReplSkin("homeassistant")
        assert skin.history_file == str(
            tmp_path / ".cli-anything-homeassistant" / "history"
        )
        assert Path(skin.history_file).parent.is_dir()

    def test_accent_color_is_homeassistant_blue(self, tmp_path):
        skin = ReplSkin("homeassistant", history_file=str(tmp_path / "h"))
        assert skin.accent == repl_skin._ACCENT_COLORS["homeassistant"]

    def test_unknown_software_gets_default_accent(self, tmp_path):
        skin = ReplSkin("whatever", history_file=str(tmp_path / "h"))
        assert skin.accent == repl_skin._DEFAULT_ACCENT


# ────────────────────────────────────────────────────────────── color support


class TestColorSupport:
    def test_no_color_env_disables_color(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NO_COLOR", "1")
        assert ReplSkin("ha", history_file=str(tmp_path / "h"))._color is False

    def test_cli_anything_no_color_env_disables_color(self, monkeypatch, tmp_path):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("CLI_ANYTHING_NO_COLOR", "1")
        assert ReplSkin("ha", history_file=str(tmp_path / "h"))._color is False

    def test_non_tty_stdout_disables_color(self, monkeypatch, tmp_path):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("CLI_ANYTHING_NO_COLOR", raising=False)
        assert ReplSkin("ha", history_file=str(tmp_path / "h"))._color is False

    def test_tty_stdout_enables_color(self, monkeypatch, tmp_path):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("CLI_ANYTHING_NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", FakeTty())
        assert ReplSkin("ha", history_file=str(tmp_path / "h"))._color is True

    def test_c_applies_color_only_when_supported(self, tmp_path):
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        skin._color = True
        assert skin._c("\033[1m", "x") == "\033[1mx\033[0m"
        skin._color = False
        assert skin._c("\033[1m", "x") == "x"


# ──────────────────────────────────────────────────────────────── banner/prompt


class TestBannerAndPrompt:
    def test_print_banner_contains_branding(self, capsys, tmp_path):
        skin = ReplSkin("homeassistant", version="9.9.9", history_file=str(tmp_path / "h"))
        skin.print_banner()
        out = capsys.readouterr().out
        assert "cli-anything" in out
        assert "Homeassistant" in out
        assert "v9.9.9" in out
        assert "Type help for commands" in out

    def test_banner_box_lines_are_padded_to_inner_width(self, capsys, tmp_path):
        """Every box line's visible width is exactly inner + the two rails."""
        skin = ReplSkin("homeassistant", history_file=str(tmp_path / "h"))
        skin._color = False
        skin.print_banner()
        lines = [ln for ln in capsys.readouterr().out.splitlines() if "│" in ln]
        assert lines, "no box lines were printed"
        assert {len(ln) for ln in lines} == {72 + 2}

    def test_prompt_plain_when_no_color(self, capsys, tmp_path):
        skin = ReplSkin("homeassistant", history_file=str(tmp_path / "h"))
        skin._color = False
        assert skin.prompt() == "> homeassistant ❯ "

    def test_prompt_shows_project_and_modified_marker(self, tmp_path):
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        skin._color = False
        p = skin.prompt(project_name="cfg.yaml", modified=True)
        assert "[cfg.yaml*]" in p
        p2 = skin.prompt(context="entity light.tv")
        assert "[entity light.tv]" in p2
        p3 = skin.prompt(project_name="a", modified=False)
        assert "*" not in p3

    def test_prompt_uses_icon_when_color(self, tmp_path):
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        skin._color = True
        assert "◆" in skin.prompt()

    def test_prompt_tokens_shape(self, tmp_path):
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        tokens = skin.prompt_tokens(project_name="p", modified=True)
        styles = [s for s, _ in tokens]
        assert styles == ["class:icon", "class:software", "class:bracket",
                          "class:context", "class:bracket", "class:arrow"]
        assert tokens[-1][1] == " ❯ "

    def test_prompt_tokens_without_context(self, tmp_path):
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        tokens = skin.prompt_tokens()
        assert ("class:software", "ha") in tokens
        assert not any(s == "class:context" for s, _ in tokens)

    def test_get_prompt_style_returns_style(self, tmp_path):
        pytest.importorskip("prompt_toolkit")
        skin = ReplSkin("ha", history_file=str(tmp_path / "h"))
        style = skin.get_prompt_style()
        assert style is not None


# ───────────────────────────────────────────────────────────────── messages


class TestMessages:
    @pytest.fixture()
    def skin(self, tmp_path):
        s = ReplSkin("ha", history_file=str(tmp_path / "h"))
        s._color = False
        return s

    def test_success_error_warning_info_hint_go_to_streams(self, skin, capsys):
        skin.success("saved")
        skin.warning("unsaved")
        skin.info("working")
        skin.hint("try this")
        out = capsys.readouterr().out
        assert "✓ saved" in out
        assert "⚠ unsaved" in out
        assert "● working" in out
        assert "try this" in out
        skin.error("broken")
        err = capsys.readouterr().err
        assert "✗ broken" in err

    def test_section_prints_rule_under_title(self, skin, capsys):
        skin.section("Registry")
        out = capsys.readouterr().out
        assert "Registry" in out
        assert "─" * len("Registry") in out

    def test_status_line(self, skin, capsys):
        skin.status("url", "http://x")
        assert "url:" in capsys.readouterr().out

    def test_status_block_pads_keys(self, skin, capsys):
        skin.status_block({"a": "1", "longer": "2"}, title="Block")
        out = capsys.readouterr().out
        assert "a" in out and "longer" in out and "Block" in out

    def test_status_block_empty_is_safe(self, skin, capsys):
        skin.status_block({})
        assert capsys.readouterr().out == ""

    def test_progress_bar_fills_and_percentages(self, skin, capsys):
        skin.progress(5, 10, label="half")
        out = capsys.readouterr().out
        assert "50%" in out
        assert "█" in out and "░" in out
        assert "half" in out

    def test_progress_zero_total_does_not_divide(self, skin, capsys):
        skin.progress(0, 0)
        assert "0%" in capsys.readouterr().out


# ────────────────────────────────────────────────────────────────── table/help


class TestTableAndHelp:
    @pytest.fixture()
    def skin(self, tmp_path):
        s = ReplSkin("ha", history_file=str(tmp_path / "h"))
        s._color = False
        return s

    def test_table_renders_headers_and_rows(self, skin, capsys):
        skin.table(["Entity", "State"], [["light.tv", "on"]])
        out = capsys.readouterr().out
        assert "Entity" in out and "light.tv" in out

    def test_table_truncates_wide_cells(self, skin, capsys):
        skin.table(["h"], [["x" * 100]], max_col_width=10)
        out = capsys.readouterr().out
        assert "x" * 11 not in out

    def test_table_without_headers_is_a_noop(self, skin, capsys):
        skin.table([], [["r"]])
        assert capsys.readouterr().out == ""

    def test_table_row_shorter_than_headers(self, skin, capsys):
        skin.table(["a", "b"], [["only"]])
        assert "only" in capsys.readouterr().out

    def test_help_lists_commands(self, skin, capsys):
        skin.help({"states": "list states", "area ls": "list areas"})
        out = capsys.readouterr().out
        assert "Commands" in out
        assert "states" in out and "area ls" in out

    def test_help_empty_dict_is_safe(self, skin, capsys):
        skin.help({})
        assert "Commands" in capsys.readouterr().out

    def test_print_goodbye(self, skin, capsys):
        skin.print_goodbye()
        assert "Goodbye!" in capsys.readouterr().out


# ─────────────────────────────────────────────────── session / input / toolbar


class TestSessionInputToolbar:
    @pytest.fixture()
    def skin(self, tmp_path):
        return ReplSkin("ha", history_file=str(tmp_path / "h"))

    def test_create_prompt_session_returns_session(self, skin):
        pytest.importorskip("prompt_toolkit")
        session = skin.create_prompt_session()
        assert session is not None

    def test_get_input_uses_prompt_toolkit_session(self, skin):
        pytest.importorskip("prompt_toolkit")

        class FakeSession:
            def __init__(self):
                self.seen = None

            def prompt(self, tokens):
                self.seen = list(tokens)
                return "  area ls \n"

        fs = FakeSession()
        assert skin.get_input(fs, project_name="p") == "area ls"
        assert ("class:software", "ha") in fs.seen

    def test_get_input_falls_back_to_input(self, skin, monkeypatch):
        prompts: list[str] = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return "quit "

        monkeypatch.setattr("builtins.input", fake_input)
        assert skin.get_input(None, project_name="p") == "quit"
        assert prompts, "input() was called without a prompt"

    def test_bottom_toolbar_builds_formatted_text(self, skin):
        pytest.importorskip("prompt_toolkit")
        toolbar = skin.bottom_toolbar({"url": "http://x", "user": "me"})
        parts = toolbar()
        texts = [t for _, t in parts]
        assert " url: " in texts[0]
        assert "http://x" in texts[1]
        assert "  │  " in texts  # separator between the two items
        assert "me" in texts
