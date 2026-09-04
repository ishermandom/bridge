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
from session_analysis.sheet_dewarp import Quad, dewarp_sheet
from session_analysis.strip_cutting import cut_strips
from session_analysis.unreviewed.rule_grid import SheetGeometryError
from session_analysis.unreviewed.sheet_geometry import (
  SheetGeometry,
  resolve_sheet_geometry,
)
from session_analysis.unreviewed.sheet_structure import read_sheet_structure
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
  """Dewarp, resolve the grid, cut strips once, and transcribe twice.

  The extraction entry point for one scan. The grid is resolved once, from a
  reading of the sheet's layout (`sheet_structure`) measured against its printed
  rules (`sheet_geometry`), and the strips are cut once from it; the model then
  reads those same strips twice, independently, for `assembly.
  parse_and_assemble_voted_session` to compare — see spec.md
  `#extraction-voting` for why two independent reads beat one. Both the row
  count and the layout come from the scan itself, so a form this pipeline has
  never seen transcribes without configuration.

  Raises:
    SheetStructureError: the sheet's layout could not be read.
    SheetGeometryError: the printed rules could not be resolved against that
      reading, so the two disagree about the sheet.
    VisionModelInvocationError: a headless `claude` invocation failed.
  """
  dewarped = dewarp_sheet(image)
  # What the sheet is made of, then where its rules are: the vision model reads
  # the layout and `sheet_geometry` measures it. Read before the strips are cut,
  # because the reading is what says which rules to cut between.
  structure = read_sheet_structure(
    dewarped.image, model=model, run_command=run_command
  )
  try:
    geometry = resolve_sheet_geometry(
      dewarped.image, structure.panels, structure.footer
    )
  except SheetGeometryError as error:
    # The model said how many board rows each panel holds and where it sits;
    # `resolve_sheet_geometry` went looking for the printed rules bounding that
    # many rows, evenly pitched, in that place — and found no run it could
    # match, or two it could not choose between. That is the one moment when the
    # model's notes on this sheet earn a person's time: an overprint hiding
    # rules, a layout it could not place. The notes join the message rather than
    # a log, because the message is what reaches the failure sidecar.
    model_notes = (
      f'; the model noted: {structure.notes}' if structure.notes else ''
    )
    raise SheetGeometryError(f'{error}{model_notes}') from error
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
