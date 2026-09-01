# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Stand-in provenance for tests whose subject is not the scan.

`Source` carries where a scan lives, what its bytes hash to, and the frame it
was read through — a full `SheetGeometry` and corner `Quad`. Assembly, voting,
and matching all need a `Source` to build a `Session` at all, and none of them
assert anything about it. Spelling out a detected grid in each of those tests
would bury what they are actually about, so they take one from here.

A test that does assert on provenance should build its own, or pass the values
it asserts on to `sheet_source` — the frame is the only part this hides.

Every value here is deliberately unlike anything the image pipeline produces:
the page is no size a synthetic scan is drawn at, the row box sits nowhere a
drawn rule falls, and the quad is skewed and fractional where a drawn grid's is
square and whole. A test whose assertion turns on the frame therefore cannot
quietly pass while taking this stand-in — it has to pass its own, keeping those
numbers beside the assertions that depend on them. `synthetic_scans` chooses its
default grid the same way and for the same reason.
"""

from session_analysis.models import SheetFrame, SheetImage, Source
from session_analysis.sheet_dewarp import Point, Quad
from session_analysis.sheet_geometry import Box, SheetGeometry


def sheet_frame() -> SheetFrame:
  """A one-row detected frame — the smallest a `SheetGeometry` may hold.

  The page size, the row box, and the quad's corners share no number with a
  drawn sheet's, and the quad is skewed off-axis where a real detection over a
  drawn grid comes back square. Nothing that reads a frame can mistake this one
  for a detected one.
  """
  return SheetFrame(
    geometry=SheetGeometry(
      image_width=317,
      image_height=419,
      row_boxes=(Box(left=11, top=23, right=306, bottom=61),),
    ),
    source_quad=Quad(
      top_left=Point(x=9.5, y=19.5),
      bottom_left=Point(x=12.5, y=402.5),
      bottom_right=Point(x=304.5, y=399.5),
      top_right=Point(x=301.5, y=16.5),
    ),
  )


def sheet_source(
  *,
  path: str = 'stand-in-scan.png',
  content_hash: str = 'standinhash0000000000',
) -> Source:
  """Provenance for a digitized session, with a stand-in frame.

  The path names no real scan and the hash is no real digest, so a test reading
  either without having passed it announces itself rather than looking plausible
  — a stem built from this hash reads `unnamed-standinhash`.
  """
  return Source(
    image=SheetImage(path=path, content_hash=content_hash, frame=sheet_frame())
  )
