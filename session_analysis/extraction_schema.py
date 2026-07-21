# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The JSON Schema the vision model's structured output must satisfy.

Passed to `vision_model_invocation.invoke_vision_model` as `json_schema` and
enforced by the CLI's `--json-schema` validation. This is the strict wire
contract; the parser side (`assembly.RawSheet`) stays deliberately lenient, so
the two are written separately rather than one derived from the other.

The whole transcription sits under a single top-level `sheet` key. Models
deliver tool input as `{parameter_name: payload}` so reliably that a schema with
`event`/`date`/`boards` at the root got wrapped under an invented key on every
observed live run, costing a correction turn each time; making the envelope
explicit matches that instinct instead of fighting it. See models.md (Vision
model output) for the full output contract.
"""

from collections.abc import Mapping

_BOARD_SCHEMA: Mapping[str, object] = {
  'type': 'object',
  'properties': {
    'board_number': {'type': 'string'},
    'auction': {'type': 'string'},
    'contract': {'type': 'string'},
    'lead': {'type': 'string'},
    'notes': {'type': 'string'},
  },
  'required': ['board_number', 'auction', 'contract', 'lead', 'notes'],
  'additionalProperties': False,
}

VISION_MODEL_OUTPUT_SCHEMA: Mapping[str, object] = {
  'type': 'object',
  'properties': {
    'sheet': {
      'type': 'object',
      'properties': {
        'event': {'type': 'string'},
        'date': {'type': 'string'},
        'boards': {'type': 'array', 'items': _BOARD_SCHEMA},
      },
      'required': ['event', 'date', 'boards'],
      'additionalProperties': False,
    },
  },
  'required': ['sheet'],
  'additionalProperties': False,
}
