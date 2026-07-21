# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Production extraction: transcribe a scan as labeled per-row strips.

The CLI downscales a full-sheet scan below legibility for dense handwriting, so
the sheet is sent as native-resolution crops instead: one labeled strip per
printed board row, cut from the detected `SheetGeometry`, plus the footer. The
labels preserve board identity, which the cutting destroys. See spec.md
(Extraction) for the design and the live comparison behind it.
"""

import io

from PIL import Image

from session_analysis.extraction_prompt import VISION_MODEL_SYSTEM_PROMPT
from session_analysis.extraction_schema import VISION_MODEL_OUTPUT_SCHEMA
from session_analysis.frozen_model import FrozenModel
from session_analysis.sheet_geometry import (
  Quad,
  SheetGeometry,
  detect_sheet_geometry,
  dewarp_sheet,
)
from session_analysis.vision_model_invocation import (
  DEFAULT_MODEL,
  CommandRunner,
  LabeledImage,
  invoke_vision_model,
  run_claude,
)

# How far a strip extends past its tight row box into each neighbor, as a
# fraction of the row pitch. The padding covers two things at once: handwriting
# routinely bleeds past the printed rules, and page curl leaves a rule drifting
# a fraction of a pitch around the median position the geometry records. The
# prompt's input-format section tells the model how to resolve the duplicated
# slivers the overlap creates.
_STRIP_PADDING_FRACTION = 0.3

_STRIP_JPEG_QUALITY = 92


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


def cut_strips(
  image: Image.Image, geometry: SheetGeometry
) -> tuple[LabeledImage, ...]:
  """Cut a scan into labeled request parts: padded row strips, then the footer.

  Each row strip expands its tight row box vertically by
  `_STRIP_PADDING_FRACTION` of the row pitch; the footer box is already sized
  with margin, so it is cut as-is.
  """
  rgb = image.convert('RGB')
  padding = round(_STRIP_PADDING_FRACTION * geometry.row_pitch())

  parts = []
  for row_number, box in enumerate(geometry.row_boxes, start=1):
    strip = rgb.crop(
      (
        box.left,
        max(0, box.top - padding),
        box.right,
        min(rgb.height, box.bottom + padding),
      )
    )
    parts.append(
      LabeledImage(
        label=f'Strip for printed row {row_number}:',
        image_bytes=_encode_jpeg(strip),
        media_type='image/jpeg',
      )
    )

  footer = rgb.crop(
    (
      geometry.footer_box.left,
      geometry.footer_box.top,
      geometry.footer_box.right,
      geometry.footer_box.bottom,
    )
  )
  parts.append(
    LabeledImage(
      label='Strip for the footer:',
      image_bytes=_encode_jpeg(footer),
      media_type='image/jpeg',
    )
  )
  return tuple(parts)


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
  crops) share. The grid's row count comes from the scan itself, so forms of
  any length transcribe without configuration.

  Raises:
    SheetGeometryError: the scan's grid could not be resolved.
    VisionModelInvocationError: the headless `claude` invocation failed.
  """
  dewarped = dewarp_sheet(image)
  geometry = detect_sheet_geometry(dewarped.image)
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


def _encode_jpeg(image: Image.Image) -> bytes:
  """Encode a cropped strip as JPEG bytes for embedding in the request."""
  buffer = io.BytesIO()
  image.save(buffer, format='JPEG', quality=_STRIP_JPEG_QUALITY)
  return buffer.getvalue()
