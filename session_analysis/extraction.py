# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The extraction stage's entry point: one scan in, its transcription out.

`transcribe_sheet` chains the stage's pieces — dewarp, grid detection, strip
cutting, and the headless model call — and returns the model's raw JSON with the
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
  MAXIMUM_TRIMMED_ROWS,
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
  """One scan's transcription: two independent reads of the same cut strips,
  plus the grid they were cut from.

  `raw_jsons` holds both runs' raw JSON, unmerged — `assembly.
  parse_and_assemble_voted_session` is what compares them cell by cell.
  `geometry` (in dewarped-image coordinates) and `source_quad` persist alongside
  the processed session, so the review UI reproduces the dewarped frame and its
  grid from the archived scan rather than re-detecting them.
  """

  raw_jsons: tuple[str, str]
  geometry: SheetGeometry
  source_quad: Quad


def transcribe_sheet(
  image: Image.Image,
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> SheetTranscription:
  """Dewarp, detect the grid, cut strips once, and transcribe twice.

  The extraction entry point for one scan: geometry detection and strip
  cutting happen once, since both are deterministic over the same image; the
  model then reads those same strips twice, independently, for `assembly.
  parse_and_assemble_voted_session` to compare — see tasks.md
  (`#extraction-voting`) for why two independent reads beat one. The grid's
  row count comes from the scan itself, so any form with a plausible row count
  (eight or more rows) transcribes without configuration.

  Raises:
    SheetGeometryError: the scan's grid could not be resolved, or the dewarp
      and detection passes disagreed on it.
    VisionModelInvocationError: a headless `claude` invocation failed.
  """
  dewarped = dewarp_sheet(image)
  geometry = detect_sheet_geometry(dewarped.image)
  # The two passes read the grid independently (raw scan vs dewarped frame).
  # Detection may legitimately run short of the dewarp's count by the rows its
  # coverage trim removed (scale charts, footer underlines); any other
  # disagreement means at least one pass misread the grid, so refuse rather than
  # send strips cut against an untrusted grid.
  trimmed_rows = dewarped.row_count - len(geometry.row_boxes)
  if not 0 <= trimmed_rows <= MAXIMUM_TRIMMED_ROWS:
    raise SheetGeometryError(
      f'the dewarp pass resolved {dewarped.row_count} rows but detection in '
      f'the dewarped frame resolved {len(geometry.row_boxes)}'
    )
  strips = cut_strips(dewarped.image, geometry)
  raw_json_a = invoke_vision_model(
    strips,
    VISION_MODEL_SYSTEM_PROMPT,
    VISION_MODEL_OUTPUT_SCHEMA,
    model=model,
    run_command=run_command,
  )
  raw_json_b = invoke_vision_model(
    strips,
    VISION_MODEL_SYSTEM_PROMPT,
    VISION_MODEL_OUTPUT_SCHEMA,
    model=model,
    run_command=run_command,
  )
  return SheetTranscription(
    raw_jsons=(raw_json_a, raw_json_b),
    geometry=geometry,
    source_quad=dewarped.source_quad,
  )
