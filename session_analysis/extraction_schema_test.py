# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Keep the wire schema aligned with the raw models that parse its output.

The schema (strict, for the vision model) and the raw models (lenient, for the
parser) are written separately by design; these tests only guard that their
field names never drift apart.
"""

from session_analysis.assembly import RawBoard, RawSession, RawSheet
from session_analysis.extraction_schema import VISION_MODEL_OUTPUT_SCHEMA


def _properties(schema: object) -> dict[str, object]:
  """Return a schema node's `properties` map, asserting it is an object."""
  assert isinstance(schema, dict)
  properties = schema['properties']
  assert isinstance(properties, dict)
  return properties


def test_the_top_level_requires_exactly_the_sheet_envelope() -> None:
  properties = _properties(VISION_MODEL_OUTPUT_SCHEMA)
  assert set(properties) == set(RawSheet.model_fields) == {'sheet'}


def test_the_sheet_fields_match_the_raw_session_model() -> None:
  sheet = _properties(VISION_MODEL_OUTPUT_SCHEMA)['sheet']
  assert set(_properties(sheet)) == set(RawSession.model_fields)


def test_the_board_fields_match_the_raw_board_model() -> None:
  sheet = _properties(VISION_MODEL_OUTPUT_SCHEMA)['sheet']
  boards = _properties(sheet)['boards']
  assert isinstance(boards, dict)
  assert set(_properties(boards['items'])) == set(RawBoard.model_fields)
