# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Cut a dewarped scan into the labeled per-row strips the model transcribes.

Sent whole, a scan reaches the vision model downscaled below legibility for
dense handwriting, so the sheet is sent as native-resolution crops instead: one
strip per printed board row, cut from the detected `SheetGeometry`, plus the
footer. Each strip is preceded by a text label naming its printed row — the
row's printed board number is inside the crop too, but the label is what pins
strip-to-row correspondence, so the model emits exactly one board object per
row strip, in order, with no counting left to chance. The footer strip carries
the event and date instead, and no board of its own. See spec.md `#extraction`
for the design and the measurements behind it.
"""

import io
from collections.abc import Sequence

from PIL import Image

from session_analysis.unreviewed.sheet_geometry import Box, SheetGeometry
from session_analysis.vision_model_invocation import LabeledImage

# How far a strip extends past its tight row box into each neighbor, as a
# fraction of the row pitch. The padding covers two things at once: handwriting
# routinely bleeds past the printed rules, and page curl leaves a rule drifting
# a fraction of a pitch around the median position the geometry records. The
# prompt's input-format section tells the model how to resolve the duplicated
# slivers the overlap creates.
_STRIP_PADDING_FRACTION = 0.3

# JPEG suits the photographic source and keeps the embedded base64 request small
# — a lossless encoding would be several times larger for no legibility gain.
# Quality 92 is the setting the strip-extraction experiments validated (see
# spec.md `#extraction`): its compression artifacts sit far below handwriting
# stroke scale.
_STRIP_JPEG_QUALITY = 92


def cut_strips(
  image: Image.Image, geometry: SheetGeometry
) -> Sequence[LabeledImage]:
  """Cut a scan into labeled request parts: padded row strips, then the footer.

  Every strip expands its tight box vertically by `_STRIP_PADDING_FRACTION` of
  the row pitch, the footer included. The footer needs the padding most: the
  band comes from the sheet's layout reading and can hug the printed guide
  underlines, which handwriting ascends above, and it is the only source of the
  session key — so clipping it costs more than clipping a board row.

  A form that prints no footer contributes no footer strip, and the sheet's
  event and date are then simply unreadable — which is what `session_keys`
  treats as an unnamed session.
  """
  rgb = image.convert('RGB')
  padding = round(_STRIP_PADDING_FRACTION * geometry.row_pitch())

  labeled_boxes = [
    (
      f'Strip for printed row {row_number}:',
      Box(
        left=box.left,
        top=max(0, box.top - padding),
        right=box.right,
        bottom=min(rgb.height, box.bottom + padding),
      ),
    )
    for row_number, box in enumerate(geometry.row_boxes, start=1)
  ]
  if geometry.footer:
    labeled_boxes.append(
      (
        'Strip for the footer:',
        Box(
          left=geometry.footer.left,
          top=max(0, geometry.footer.top - padding),
          right=geometry.footer.right,
          bottom=min(rgb.height, geometry.footer.bottom + padding),
        ),
      )
    )

  return tuple(
    LabeledImage(
      label=label,
      image_bytes=_encode_jpeg(
        rgb.crop((box.left, box.top, box.right, box.bottom))
      ),
      media_type='image/jpeg',
    )
    for label, box in labeled_boxes
  )


def _encode_jpeg(image: Image.Image) -> bytes:
  """Encode a cropped strip as JPEG bytes for embedding in the request."""
  buffer = io.BytesIO()
  image.save(buffer, format='JPEG', quality=_STRIP_JPEG_QUALITY)
  return buffer.getvalue()
