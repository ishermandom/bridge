# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Stand-in provenance for tests whose subject is not the scan.

`Source` carries where a scan lives, what its bytes hash to, and the grid read
from it — a full `SheetGeometry`. Assembly, voting, and matching all need a
`Source` to build a `Session` at all, and none of them assert anything about it.
Spelling out a detected grid in each of those tests would bury what they are
actually about, so they take one from here.

A test that does assert on provenance should build its own, or pass the values
it asserts on to `sheet_source` — the geometry is the only part this hides.

Every value here is deliberately unlike anything the image pipeline produces:
the page is no size a synthetic scan is drawn at, and the row box sits nowhere a
drawn rule falls. A test whose assertion turns on the geometry therefore cannot
quietly pass while taking this stand-in — it has to pass its own, keeping those
numbers beside the assertions that depend on them. `synthetic_scans` chooses its
default grid the same way and for the same reason.
"""

from collections.abc import Sequence

from session_analysis.models import (
  CaptureReference,
  SheetImage,
  Source,
)
from session_analysis.unreviewed.sheet_geometry import Box, SheetGeometry


def sheet_geometry() -> SheetGeometry:
  """A one-row stand-in grid — the smallest a `SheetGeometry` may hold.

  The page size and the row box share no number with a drawn sheet's, so nothing
  that reads a geometry can mistake this one for a detected one.
  """
  return SheetGeometry(
    image_width=317,
    image_height=419,
    row_boxes=(Box(left=11, top=23, right=306, bottom=61),),
  )


def sheet_source(
  *,
  path: str = 'stand-in-scan.png',
  content_hash: str = 'standinhash0000000000',
  travellers: Sequence[CaptureReference] = (),
) -> Source:
  """Provenance for a digitized session, with a stand-in geometry.

  The path names no real scan and the hash is no real digest, so a test reading
  either without having passed it announces itself rather than looking plausible
  — a stem built from this hash reads `unnamed-standinhash`.

  `travellers` defaults to none, which is the shape of a session that
  reconciliation has not reached. A test whose subject is a session joined to
  its captures passes its own.
  """
  return Source(
    image=SheetImage(
      path=path, content_hash=content_hash, geometry=sheet_geometry()
    ),
    travellers=tuple(travellers),
  )
