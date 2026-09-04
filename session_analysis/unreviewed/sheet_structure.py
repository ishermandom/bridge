# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Asking the vision model what a scoresheet's printed table is made of.

Grid detection splits cleanly in two, and this is the half a model does better.
Deciding *what* a line means — this rule bounds a board row, that one is the
footer's writing guide, those belong to a conversion chart printed above the
table — is a judgement about the form, and the ink-coverage and row-count
heuristics that used to make it were wrong on real scans: on one sheet they
refused the page outright, and on another they silently took the footer's guide
underline for the grid's last rule and pushed the footer region onto blank paper
below it, losing the event and date the session key is built from.

Deciding *where* a rule sits, to the pixel, is the other half, and `rule_grid`'s
dip detection already does it well. So this module supplies only the reading —
above all each panel's `board_row_count`, which `sheet_geometry` takes as exact
— and every coordinate in the resulting geometry still comes from a rule found
in the pixels. Measured over repeated runs the row count is exactly stable where
the coordinates drift — a panel border by up to 17px, the grid's bottom by up to
53px between runs of one page — which is why the count is a hard constraint and
the coordinates only place it.

The sheet is sent pre-scaled to the size the model will see it at, so the
coordinates it reports need no rescaling afterwards; `image_for_model` does
that, and `SCALE_LIMITS` records the limits it scales to.
"""

import io
import math
import pathlib
from collections.abc import Mapping
from typing import Annotated

import pydantic
from PIL import Image

from session_analysis.frozen_model import FrozenModel
from session_analysis.unreviewed.sheet_geometry import BoardPanel, Box
from session_analysis.vision_model_invocation import (
  DEFAULT_MODEL,
  CommandRunner,
  LabeledImage,
  invoke_vision_model,
  run_claude,
)

SHEET_STRUCTURE_SYSTEM_PROMPT: str = (
  pathlib.Path(__file__).parent / 'sheet_structure_prompt.md'
).read_text()

# The user turn that closes the request. All real instruction lives in the
# system prompt; this states the ask, as extraction's does for transcription.
_STRUCTURE_INSTRUCTION = (
  'Report the structure of the printed table in this scoresheet image.'
)

# The page is sent as JPEG at the quality the strips use — its artifacts sit
# well below the scale of a printed rule.
_PAGE_JPEG_QUALITY = 92

# The model's image limits, as (longest edge, visual tokens). An image over
# either is scaled down before the model sees it, so a coordinate it reports is
# in the scaled image's pixels; sending the already-scaled image makes the two
# spaces one. These are the high-resolution tier's published limits, which
# `DEFAULT_MODEL` is on — see the vision guide's "Resolution and token cost".
# `_check_fits` checks that they held rather than trusting them: were they
# smaller, the image would be scaled again and every coordinate would come back
# in a space this module does not know about.
SCALE_LIMITS = (2576, 4784)
# The model sees an image as patches this many pixels on a side, one visual
# token each.
_PATCH_SIZE = 28

# How far outside the sent image a reported box may lie, as a fraction of the
# image's own size, before `_check_fits` takes the reading to be of something
# else. Generous, because overhang at the edge is ordinary and clamped
# downstream; what this separates is a rounding from a reading that is not
# describing this image at all.
_OUTSIDE_FRAME_TOLERANCE = 0.05


class SheetStructureError(Exception):
  """Raised when the model's reading of a sheet does not parse."""


class SheetStructure(FrozenModel):
  """What the model made of one scoresheet's printed table."""

  # Left to right, which is the order the sheet's printed board numbers run in.
  panels: Annotated[tuple[BoardPanel, ...], pydantic.Field(min_length=1)]
  # Where the handwritten event, date and pair number sit. None on a form that
  # prints no footer — several vendor forms put conversion charts below the
  # table instead, and reading one as a footer would invent an event and date.
  footer: Box | None = None
  # Whatever the model thought worth saying about the sheet. Nothing reads it
  # automatically; it is what a person is shown when this reading and the pixels
  # disagree, so it is carried rather than discarded.
  notes: str = ''

  def rescaled(self, scale: float) -> 'SheetStructure':
    """This reading in the full-resolution image's own pixel space.

    The model reads a scaled copy (`image_for_model`), so every coordinate it
    reports is in that copy's pixels; dividing by the scale returns them to the
    sheet's own.
    """
    if scale == 1.0:
      return self
    return SheetStructure(
      panels=tuple(
        BoardPanel(
          board_row_count=panel.board_row_count,
          grid=_rescaled_box(panel.grid, scale),
        )
        for panel in self.panels
      ),
      footer=_rescaled_box(self.footer, scale) if self.footer else None,
      notes=self.notes,
    )


_PANEL_SCHEMA: Mapping[str, object] = {
  'type': 'object',
  'properties': {
    'board_row_count': {
      'type': 'integer',
      'description': "This panel's number of ruled board rows, blank trailing "
      'rows included, header row excluded.',
    },
    'grid': {
      'type': 'object',
      'description': "The panel's board rows only, excluding its header row, "
      'any printed chart, and the footer.',
      'properties': {
        'left': {'type': 'integer'},
        'top': {'type': 'integer'},
        'right': {'type': 'integer'},
        'bottom': {'type': 'integer'},
      },
      'required': ['left', 'top', 'right', 'bottom'],
      'additionalProperties': False,
    },
  },
  'required': ['board_row_count', 'grid'],
  'additionalProperties': False,
}

SHEET_STRUCTURE_OUTPUT_SCHEMA: Mapping[str, object] = {
  'type': 'object',
  'properties': {
    'panels': {
      'type': 'array',
      'minItems': 1,
      'description': 'One entry per side-by-side block of board rows, left to '
      'right. Most forms have exactly one.',
      'items': _PANEL_SCHEMA,
    },
    'footer': {
      'type': ['object', 'null'],
      'description': 'The band holding the handwritten PAIR / TEAM #, EVENT '
      'and DATE, or null on a form that prints no such footer.',
      'properties': {
        'left': {'type': 'integer'},
        'top': {'type': 'integer'},
        'right': {'type': 'integer'},
        'bottom': {'type': 'integer'},
      },
      'required': ['left', 'top', 'right', 'bottom'],
      'additionalProperties': False,
    },
    'notes': {
      'type': 'string',
      'description': 'Anything unusual about this sheet worth a person '
      'reading.',
    },
  },
  'required': ['panels', 'footer', 'notes'],
  'additionalProperties': False,
}


def read_sheet_structure(
  image: Image.Image,
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> SheetStructure:
  """Ask the model what the printed table on this sheet is made of.

  Args:
    image: the dewarped sheet, in its own full-resolution pixel space.
    model: the vision model to read with.
    run_command: how the headless invocation is run; injected so a test needs
      no model call.

  Returns:
    The reading, already returned to `image`'s own pixel space.

  Raises:
    SheetStructureError: the response did not parse as a sheet structure.
    VisionModelInvocationError: the headless model invocation failed.
  """
  scaled, scale = image_for_model(image)
  buffer = io.BytesIO()
  scaled.convert('RGB').save(buffer, format='JPEG', quality=_PAGE_JPEG_QUALITY)
  parts = (
    LabeledImage(
      label='Scoresheet:',
      image_bytes=buffer.getvalue(),
      media_type='image/jpeg',
    ),
  )
  raw_json = invoke_vision_model(
    parts,
    SHEET_STRUCTURE_SYSTEM_PROMPT,
    SHEET_STRUCTURE_OUTPUT_SCHEMA,
    model=model,
    run_command=run_command,
    instruction=_STRUCTURE_INSTRUCTION,
  )
  try:
    structure = SheetStructure.model_validate_json(raw_json)
  except pydantic.ValidationError as error:
    raise SheetStructureError(
      f'the model reading of the sheet did not parse: {error}; the response '
      f'was {raw_json[:500]}'
    ) from error
  _check_fits(structure, scaled.width, scaled.height)
  return structure.rescaled(scale)


def _check_fits(structure: SheetStructure, width: int, height: int) -> None:
  """Refuse a reading placed far outside the image that was sent.

  Far outside, not merely over the edge. A band reported flush with the page's
  bottom is the ordinary answer for a footer, and a pixel or two beyond it is
  the ordinary rounding — `sheet_geometry` clamps both, which is what `_within`
  is for. Refusing them here would lose a whole sheet to a rounding and leave
  that clamp unreachable.

  What is worth refusing is a reading that is not describing this image at all,
  which lands nowhere near its frame. It is worth being clear about what that
  does *not* catch: were `SCALE_LIMITS` wrong and the image scaled again before
  the model saw it, every coordinate would come back proportionally *smaller* —
  inside the image, and so past this check entirely. That direction is caught by
  `sheet_geometry` instead, loudly, because coordinates shrunk by a scale factor
  place the grid nowhere near the printed rules.

  The API has a guard for exactly that — an image block marked `transformations:
  {"oversized_image": "error"}` is refused rather than rescaled — but it is not
  reachable from here. Tested: an image over both limits, sent through the CLI
  with that field set, came back answered rather than refused, so the field does
  not survive the trip.

  Raises:
    SheetStructureError: a reported box lies substantially outside the image.
  """
  margin_x = _OUTSIDE_FRAME_TOLERANCE * width
  margin_y = _OUTSIDE_FRAME_TOLERANCE * height
  boxes = [panel.grid for panel in structure.panels]
  if structure.footer:
    boxes.append(structure.footer)
  for box in boxes:
    if (
      box.left < -margin_x
      or box.top < -margin_y
      or box.right > width + margin_x
      or box.bottom > height + margin_y
    ):
      raise SheetStructureError(
        f'the reading places {box} outside the {width}x{height} image it was '
        f"given, so its coordinates are not in that image's pixels"
      )


def image_for_model(image: Image.Image) -> tuple[Image.Image, float]:
  """The image at exactly the size the model sees, and the scale applied.

  An image over the model's limits is scaled down before it is read, so a
  coordinate the model reports is in the scaled copy's pixels rather than the
  original's. Scaling here instead makes the two spaces one, which is the
  documented way to keep reported coordinates usable.
  """
  target = _scaled_size(image.width, image.height, *SCALE_LIMITS)
  if target == image.size:
    return image, 1.0
  return image.resize(target, Image.Resampling.LANCZOS), target[0] / image.width


def _scaled_size(
  width: int, height: int, max_edge: int, max_tokens: int
) -> tuple[int, int]:
  """The size an image is scaled to before the model sees it.

  The largest size at the image's own aspect ratio whose edges are both within
  `max_edge` and whose visual token cost — one token per `_PATCH_SIZE` square —
  is within `max_tokens`. For page-shaped images it is the token limit that
  binds, never the edge.
  """

  def fits(candidate_width: int, candidate_height: int) -> bool:
    wide = math.ceil(candidate_width / _PATCH_SIZE)
    tall = math.ceil(candidate_height / _PATCH_SIZE)
    return (
      wide * _PATCH_SIZE <= max_edge
      and tall * _PATCH_SIZE <= max_edge
      and wide * tall <= max_tokens
    )

  if fits(width, height):
    return (width, height)
  if height > width:
    tall_height, tall_width = _scaled_size(height, width, max_edge, max_tokens)
    return (tall_width, tall_height)

  # Binary search along the long edge for the largest size that still fits.
  aspect_ratio = width / height
  fitting, too_large = 1, width
  while fitting + 1 < too_large:
    candidate = (fitting + too_large) // 2
    if fits(candidate, max(round(candidate / aspect_ratio), 1)):
      fitting = candidate
    else:
      too_large = candidate
  return (fitting, max(round(fitting / aspect_ratio), 1))


def _rescaled_box(box: Box, scale: float) -> Box:
  """One reported box in the full-resolution image's own pixel space."""
  return Box(
    left=round(box.left / scale),
    top=round(box.top / scale),
    right=round(box.right / scale),
    bottom=round(box.bottom / scale),
  )
