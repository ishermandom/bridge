# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The extraction stage's entry point: one scan in, its transcription out.

`transcribe_sheet` chains the stage's pieces — the dewarp (`sheet_dewarp`), grid
detection (`sheet_geometry`), strip cutting (`strip_cutting`), and the headless
model call (`vision_model_invocation`, prompted by `extraction_prompt` and
constrained by `extraction_schema`) — and returns the model's raw JSON with the
geometry artifacts later consumers share. Parsing that JSON into the canonical
model is deliberately not part of the stage: it belongs to `assembly`, which
never touches images.
"""

from PIL import Image

from session_analysis.extraction_prompt import VISION_MODEL_SYSTEM_PROMPT
from session_analysis.extraction_schema import VISION_MODEL_OUTPUT_SCHEMA
from session_analysis.frozen_model import FrozenModel
from session_analysis.rule_grid import SheetGeometryError
from session_analysis.sheet_dewarp import Quad, dewarp_sheet
from session_analysis.sheet_geometry import (
  SheetGeometry,
  detect_sheet_geometry,
)
from session_analysis.strip_cutting import cut_strips
from session_analysis.vision_model_invocation import (
  DEFAULT_MODEL,
  CommandRunner,
  invoke_vision_model,
  run_claude,
)


class SheetTranscription(FrozenModel):
  """One scan's transcription: the model's raw JSON plus the grid it was cut
  from.

  `raw_json` feeds `assembly.parse_and_assemble_session`. `geometry` (in
  dewarped-image coordinates) and `source_quad` persist alongside the processed
  session, so voting reruns and the review UI reproduce the dewarped frame and
  its grid from the archived scan rather than re-detecting them.
  """

  raw_json: str
  geometry: SheetGeometry
  source_quad: Quad


def transcribe_sheet(
  image: Image.Image,
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> SheetTranscription:
  """Dewarp, detect the grid, cut strips, and run one transcription.

  The extraction entry point for one scan: the returned `raw_json` is what
  `assembly.parse_and_assemble_session` consumes, and the returned geometry
  and source quad are the artifacts later consumers (voting reruns, review
  crops) share. The grid's row count comes from the scan itself, so any form
  with a plausible row count (eight or more rows) transcribes without
  configuration.

  Raises:
    SheetGeometryError: the scan's grid could not be resolved, or the dewarp
      and detection passes disagreed on it.
    VisionModelInvocationError: the headless `claude` invocation failed.
  """
  dewarped = dewarp_sheet(image)
  geometry = detect_sheet_geometry(dewarped.image)
  # The two passes read the grid independently (raw scan vs dewarped frame); a
  # disagreement means at least one misread it, so refuse rather than send
  # strips cut against an untrusted grid.
  if len(geometry.row_boxes) != dewarped.row_count:
    raise SheetGeometryError(
      f'the dewarp pass resolved {dewarped.row_count} rows but detection in '
      f'the dewarped frame resolved {len(geometry.row_boxes)}'
    )
  raw_json = invoke_vision_model(
    cut_strips(dewarped.image, geometry),
    VISION_MODEL_SYSTEM_PROMPT,
    VISION_MODEL_OUTPUT_SCHEMA,
    model=model,
    run_command=run_command,
  )
  return SheetTranscription(
    raw_json=raw_json, geometry=geometry, source_quad=dewarped.source_quad
  )
