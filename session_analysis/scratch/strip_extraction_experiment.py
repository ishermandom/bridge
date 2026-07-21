# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Strip-based extraction experiment: per-row crops at native resolution.

The validated prototype behind the strip-based extraction task in tasks.md. Cuts
the 6/29 scan into one native-resolution strip per printed board row (plus the
footer), sends them as a labeled multi-image request, and prints the result and
cost. The row geometry is hand-tuned to this one scan; production replaces it
with per-scan grid detection.

Run with: `uv run --with pillow python strip_extraction_experiment.py`
"""

import base64
import json
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

from session_analysis import vision_model_invocation
from session_analysis.extraction_prompt import VISION_MODEL_SYSTEM_PROMPT
from session_analysis.extraction_schema import VISION_MODEL_OUTPUT_SCHEMA

SCAN_PATH = pathlib.Path(
  '/Users/Shared/code/bridge-private/scoresheets/PXL_20260630_191216837.jpg'
)
MODEL = 'claude-opus-4-8'

# Hand-tuned row geometry for this scan (3000x4000). Row i's top edge in
# original pixels; each strip is 105px tall and spans x 140-3000 so the printed
# `Bd` column is included — without it the model substitutes the adjacent `Vs`
# number for the board number.
ROW_COUNT = 28
FIRST_ROW_DISPLAY_Y = 185
ROW_PITCH_DISPLAY = 37.53
DISPLAY_TO_ORIGINAL = 2
ROW_CROP = {'left': 140, 'right': 3000, 'height': 105, 'top_nudge': -12}
FOOTER_CROP = (200, 2470, 2500, 2600)

# Appended to the production prompt: the labels fix board identity, and the
# explicit blank-row instruction stops the model skipping empty rows.
STRIP_PROMPT_ADDENDUM = """
## Input format for this run

The sheet arrives as horizontal strips cut from one scan at full resolution:
one strip per printed board row, each preceded by a text label naming the
printed row it shows, followed by a final strip of the footer. Adjacent strips
overlap a little vertically — transcribe each board row from the strip whose
middle line it occupies, and emit one board object per row strip, blank rows
included.
"""


def row_top(row: int) -> int:
  """Return row `row`'s strip top edge in original-image pixels."""
  display_y = FIRST_ROW_DISPLAY_Y + (row - 1) * ROW_PITCH_DISPLAY
  return round(display_y * DISPLAY_TO_ORIGINAL) + ROW_CROP['top_nudge']


def cut_strips(strips_dir: pathlib.Path) -> list[pathlib.Path]:
  """Cut per-row and footer strips from the scan into `strips_dir`."""
  image = Image.open(SCAN_PATH)
  strips_dir.mkdir(parents=True, exist_ok=True)
  paths = []
  for row in range(1, ROW_COUNT + 1):
    top = row_top(row)
    path = strips_dir / f'row_{row:02d}.jpg'
    image.crop(
      (ROW_CROP['left'], top, ROW_CROP['right'], top + ROW_CROP['height'])
    ).save(path, quality=92)
    paths.append(path)
  footer_path = strips_dir / 'footer.jpg'
  image.crop(FOOTER_CROP).save(footer_path, quality=92)
  paths.append(footer_path)
  return paths


def build_request(strip_paths: list[pathlib.Path]) -> str:
  """Return the stream-json request line carrying the labeled strips."""
  content: list[dict[str, object]] = []
  for path in strip_paths:
    label = (
      'Strip for the footer:'
      if path.stem == 'footer'
      else f'Strip for printed row {int(path.stem.removeprefix("row_"))}:'
    )
    content.append({'type': 'text', 'text': label})
    content.append(
      {
        'type': 'image',
        'source': {
          'type': 'base64',
          'media_type': 'image/jpeg',
          'data': base64.b64encode(path.read_bytes()).decode('ascii'),
        },
      }
    )
  content.append({'type': 'text', 'text': 'Transcribe the attached scan.'})
  message = {'type': 'user', 'message': {'role': 'user', 'content': content}}
  return json.dumps(message) + '\n'


def main() -> None:
  strips_dir = pathlib.Path(__file__).parent / 'strips'
  request = build_request(cut_strips(strips_dir))
  command = [
      'claude', '-p',
      '--model', MODEL,
      '--system-prompt', VISION_MODEL_SYSTEM_PROMPT + STRIP_PROMPT_ADDENDUM,
      '--tools', '',
      '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
      '--setting-sources', '',
      '--input-format', 'stream-json',
      '--output-format', 'stream-json',
      '--verbose',
      '--json-schema', json.dumps(dict(VISION_MODEL_OUTPUT_SCHEMA)),
      '--max-turns', '3',
  ]  # fmt: skip
  process = vision_model_invocation.run_claude(
    command, request, vision_model_invocation._SCRATCH_DIRECTORY
  )
  for line in process.stdout.splitlines():
    event = json.loads(line)
    if event.get('type') == 'result':
      print('cost USD:', event.get('total_cost_usd'))
      print(json.dumps(json.loads(event.get('result') or '{}'), indent=2))


if __name__ == '__main__':
  main()
