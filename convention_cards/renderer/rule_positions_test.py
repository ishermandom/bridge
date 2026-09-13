# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Tests for the measured rule positions."""

from renderer.measure_rule_positions import measure_rule_tops
from renderer.private_paths import discover_private_assets
from renderer.rule_positions import RULE_TOPS
from renderer.vocabulary import VOCABULARY, TextEntry


def test_the_table_matches_a_fresh_measurement() -> None:
  # The table is the measuring script's committed output, so a mismatch means
  # the base card or the measuring code changed without regenerating it.
  base_pdf = discover_private_assets().base_acbl_card_pdf.read_bytes()

  assert measure_rule_tops(base_pdf) == RULE_TOPS


def test_every_text_entry_field_has_a_measured_rule() -> None:
  text_fields = {
    target.field_name
    for target in VOCABULARY.values()
    if isinstance(target, TextEntry)
  }

  assert text_fields <= set(RULE_TOPS)
