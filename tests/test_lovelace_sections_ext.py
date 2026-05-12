"""Unit tests for lovelace_sections_ext — sections-view section polish helpers.

Tests cover:
  - Happy-path output for all four builder functions.
  - In-place mutation behavior of with_section_options.
  - Validation for each input parameter and error branch.
"""

from __future__ import annotations

import pytest

from cli_anything.homeassistant.core import lovelace_sections_ext


class TestSectionsPolish:
    """Tests for section polish helpers."""

    # ────────────────────────────────────────── with_section_options happy path

    def test_with_section_options_all_fields(self):
        """Test setting all fields at once."""
        section = {"type": "grid", "cards": []}
        result = lovelace_sections_ext.with_section_options(
            section,
            heading_style="title",
            top_margin=True,
            column_span=2,
            row_span=3,
        )
        assert result is section, "should return the same dict (mutation)"
        assert section["heading_style"] == "title"
        assert section["top_margin"] is True
        assert section["column_span"] == 2
        assert section["row_span"] == 3

    def test_with_section_options_partial_fields(self):
        """Test setting only some fields — others stay as-is."""
        section = {"type": "grid", "cards": []}
        result = lovelace_sections_ext.with_section_options(
            section,
            heading_style="subtitle",
            column_span=1,
        )
        assert section["heading_style"] == "subtitle"
        assert section["column_span"] == 1
        assert "top_margin" not in section
        assert "row_span" not in section

    def test_with_section_options_no_fields(self):
        """Test calling with all None — section unchanged."""
        section = {"type": "grid", "cards": []}
        original = dict(section)
        result = lovelace_sections_ext.with_section_options(section)
        assert section == original
        assert result is section

    def test_with_section_options_mutates_in_place(self):
        """Confirm that the function mutates the original dict."""
        section = {}
        result = lovelace_sections_ext.with_section_options(
            section, heading_style="default"
        )
        assert id(result) == id(section)
        assert section["heading_style"] == "default"

    # ────────────────────────────────────────── with_section_options validation

    def test_with_section_options_not_a_dict(self):
        """Raise if section is not a dict."""
        with pytest.raises(ValueError, match="section must be a dict"):
            lovelace_sections_ext.with_section_options("not a dict")

    def test_with_section_options_invalid_heading_style(self):
        """Raise if heading_style not in {title, subtitle, default}."""
        section = {}
        with pytest.raises(
            ValueError,
            match="heading_style must be 'title', 'subtitle', or 'default'",
        ):
            lovelace_sections_ext.with_section_options(
                section, heading_style="invalid"
            )

    def test_with_section_options_invalid_column_span(self):
        """Raise if column_span not in {1, 2, 3, 4}."""
        section = {}
        with pytest.raises(ValueError, match="column_span must be 1-4"):
            lovelace_sections_ext.with_section_options(
                section, column_span=5
            )

    def test_with_section_options_invalid_row_span_zero(self):
        """Raise if row_span is 0 or negative."""
        section = {}
        with pytest.raises(ValueError, match="row_span must be > 0"):
            lovelace_sections_ext.with_section_options(
                section, row_span=0
            )

    def test_with_section_options_invalid_row_span_negative(self):
        """Raise if row_span is negative."""
        section = {}
        with pytest.raises(ValueError, match="row_span must be > 0"):
            lovelace_sections_ext.with_section_options(
                section, row_span=-1
            )

    def test_with_section_options_invalid_row_span_not_int(self):
        """Raise if row_span is not an integer."""
        section = {}
        with pytest.raises(ValueError, match="row_span must be > 0"):
            lovelace_sections_ext.with_section_options(
                section, row_span="not an int"
            )

    # ────────────────────────────────────────── hero_section happy path

    def test_hero_section_defaults(self):
        """Test hero_section with default parameters."""
        card = {"type": "heading", "heading": "Hero"}
        result = lovelace_sections_ext.hero_section(card=card)
        assert result["type"] == "grid"
        assert result["cards"] == [card]
        assert result["heading_style"] == "title"
        assert result["column_span"] == 4
        assert result["top_margin"] is False

    def test_hero_section_custom_options(self):
        """Test hero_section with custom span, style, and margin."""
        card = {"type": "custom:button-card"}
        result = lovelace_sections_ext.hero_section(
            card=card,
            column_span=2,
            heading_style="subtitle",
            top_margin=True,
        )
        assert result["type"] == "grid"
        assert result["cards"] == [card]
        assert result["heading_style"] == "subtitle"
        assert result["column_span"] == 2
        assert result["top_margin"] is True

    def test_hero_section_single_card_wrapped(self):
        """Confirm that the card is wrapped in a cards list."""
        card = {"type": "markdown", "content": "Hello"}
        result = lovelace_sections_ext.hero_section(card=card)
        assert len(result["cards"]) == 1
        assert result["cards"][0] is card

    # ────────────────────────────────────────── hero_section validation

    def test_hero_section_card_not_dict(self):
        """Raise if card is not a dict."""
        with pytest.raises(
            ValueError, match="card must be a dict with a `type` field"
        ):
            lovelace_sections_ext.hero_section(card="not a dict")

    def test_hero_section_card_missing_type(self):
        """Raise if card has no type field."""
        with pytest.raises(
            ValueError, match="card must be a dict with a `type` field"
        ):
            lovelace_sections_ext.hero_section(card={})

    def test_hero_section_invalid_column_span(self):
        """Raise if column_span not in {1, 2, 3, 4}."""
        card = {"type": "heading"}
        with pytest.raises(ValueError, match="column_span must be 1-4"):
            lovelace_sections_ext.hero_section(card=card, column_span=5)

    def test_hero_section_invalid_heading_style(self):
        """Raise if heading_style not in {title, subtitle, default}."""
        card = {"type": "heading"}
        with pytest.raises(
            ValueError,
            match="heading_style must be 'title', 'subtitle', or 'default'",
        ):
            lovelace_sections_ext.hero_section(
                card=card, heading_style="bad"
            )

    # ────────────────────────────────────────── spacer_section happy path

    def test_spacer_section_defaults(self):
        """Test spacer_section with default column_span."""
        result = lovelace_sections_ext.spacer_section()
        assert result["type"] == "grid"
        assert result["cards"] == []
        assert result["column_span"] == 4

    def test_spacer_section_custom_span(self):
        """Test spacer_section with custom column_span."""
        result = lovelace_sections_ext.spacer_section(column_span=2)
        assert result["type"] == "grid"
        assert result["cards"] == []
        assert result["column_span"] == 2

    def test_spacer_section_empty_cards(self):
        """Confirm that spacer always has an empty cards list."""
        result = lovelace_sections_ext.spacer_section()
        assert isinstance(result["cards"], list)
        assert len(result["cards"]) == 0

    # ────────────────────────────────────────── spacer_section validation

    def test_spacer_section_invalid_column_span(self):
        """Raise if column_span not in {1, 2, 3, 4}."""
        with pytest.raises(ValueError, match="column_span must be 1-4"):
            lovelace_sections_ext.spacer_section(column_span=0)

    # ────────────────────────────────────────── divider_section happy path

    def test_divider_section_defaults(self):
        """Test divider_section with default column_span."""
        result = lovelace_sections_ext.divider_section(label="Settings")
        assert result["type"] == "grid"
        assert len(result["cards"]) == 1
        assert result["cards"][0]["type"] == "heading"
        assert result["cards"][0]["heading"] == "Settings"
        assert result["column_span"] == 4

    def test_divider_section_custom_span(self):
        """Test divider_section with custom column_span."""
        result = lovelace_sections_ext.divider_section(
            label="Divider", column_span=1
        )
        assert result["type"] == "grid"
        assert result["cards"][0]["heading"] == "Divider"
        assert result["column_span"] == 1

    def test_divider_section_label_preserved(self):
        """Confirm that label is used as heading text."""
        label = "My Section"
        result = lovelace_sections_ext.divider_section(label=label)
        assert result["cards"][0]["heading"] == label

    # ────────────────────────────────────────── divider_section validation

    def test_divider_section_empty_label(self):
        """Raise if label is empty."""
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            lovelace_sections_ext.divider_section(label="")

    def test_divider_section_whitespace_only_label(self):
        """Raise if label is whitespace-only."""
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            lovelace_sections_ext.divider_section(label="   ")

    def test_divider_section_label_not_string(self):
        """Raise if label is not a string."""
        with pytest.raises(ValueError, match="label must be a non-empty string"):
            lovelace_sections_ext.divider_section(label=123)

    def test_divider_section_invalid_column_span(self):
        """Raise if column_span not in {1, 2, 3, 4}."""
        with pytest.raises(ValueError, match="column_span must be 1-4"):
            lovelace_sections_ext.divider_section(label="Test", column_span=7)

    # ────────────────────────────────────────── integration / edge cases

    def test_hero_and_spacer_combined(self):
        """Test that hero and spacer produce compatible section shapes."""
        hero = lovelace_sections_ext.hero_section(
            card={"type": "heading"}
        )
        spacer = lovelace_sections_ext.spacer_section()
        # Both should be type:grid sections
        assert hero["type"] == spacer["type"] == "grid"
        assert "cards" in hero and "cards" in spacer

    def test_divider_with_polish_options(self):
        """Test that divider output can be further polished."""
        divider = lovelace_sections_ext.divider_section(label="Break")
        polished = lovelace_sections_ext.with_section_options(
            divider, heading_style="subtitle", top_margin=True
        )
        assert polished["heading_style"] == "subtitle"
        assert polished["top_margin"] is True
        # Original label should survive
        assert polished["cards"][0]["heading"] == "Break"

    def test_all_column_spans_valid(self):
        """Verify all valid column_span values work."""
        for span in (1, 2, 3, 4):
            section = lovelace_sections_ext.spacer_section(column_span=span)
            assert section["column_span"] == span

    def test_all_heading_styles_valid(self):
        """Verify all valid heading_style values work."""
        section = {}
        for style in ("title", "subtitle", "default"):
            result = lovelace_sections_ext.with_section_options(
                section, heading_style=style
            )
            assert section["heading_style"] == style
