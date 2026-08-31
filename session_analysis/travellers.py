# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The captured game record: one traveller per source per session.

A traveller is the official record of a session — every table's play of every
board, plus the deal and the double-dummy analysis that ride along with it. It
is a game database in its own right, not merely a lookup consulted while
checking a sheet: it stands for sessions no sheet was kept for, and it carries
the deal, which no sheet records at all. Reconciliation joins it to a digitized
sheet; see travellers.md.

Every source condenses the same facts its own way — a level here, a trick count
there, a score printed once per side or once signed. The parsers normalize all
of it into the shapes below, so two sources covering one session become directly
comparable and a disagreement between them surfaces as a disagreement rather
than as a difference in spelling.

Nothing a capture says is thrown away for being unreadable — the same discipline
the sheet models hold to (see models.md `#nothing-is-garbage`). A parser that
cannot read one row keeps the rest and records an `Issue` where the failure
happened, so reconciliation surfaces it beside every other thing worth a
person's attention. Travellers are machine-generated and so rarely malformed —
but rarely is not never, and losing a whole capture's four hundred rows to one
odd cell is the worse failure.
"""

import datetime
import enum
from collections.abc import Mapping

from session_analysis.enums import Direction, Strain
from session_analysis.frozen_model import FrozenModel
from session_analysis.models import Card, Deal, Issue, PairIdentity, Resolution


class TravellerSource(enum.StrEnum):
  """Where a traveller was captured from.

  The `CLUB_` surfaces are the Palo Alto club's own site, which publishes each
  game as both a PBN and an HTML page. The two ACBL surfaces are named apart
  because they publish different markup and cover different events, not because
  the records differ once parsed.
  """

  CLUB_PBN = 'club_pbn'
  CLUB_HTML = 'club_html'
  ACBL_CLUB = 'acbl_club'
  ACBL_TOURNAMENT = 'acbl_tournament'


# How many tricks each declarer takes in each strain against best defense —
# twenty cells, keyed by seat and then by strain. Sources state some cells as a
# level and some as a count; this holds the count throughout, so they compare
# directly.
#
# A cell is None only where its source declined to say. The club's HTML lists
# makeable contracts alone, so it leaves every cell below seven tricks unstated
# — None there is the honest value, since "fewer than seven" is all it said. The
# club's PBN and both ACBL surfaces state all twenty exactly.
DoubleDummyTricks = Mapping[Direction, Mapping[Strain, int | None]]


class Par(FrozenModel):
  """The double-dummy par: the score best play by both sides arrives at.

  `score` is from North-South's perspective, as every source prints it, and sits
  apart from the contracts because one score is shared by all of them.

  `resolutions` holds the contracts that achieve it, reusing the same union a
  played board resolves to: par is the contract optimal bidding would reach and
  play, so a contract paired with its result is exactly the right shape, and a
  deal where nothing makes pars at a `Passout`. A source that states par for a
  whole side is expanded to one contract per seat — both seats achieve the
  score, so expanding loses nothing and spares every reader the special case.
  """

  score: int
  resolutions: tuple[Resolution, ...]


class TravellerResult(FrozenModel):
  """One table's play of one board.

  A row with no `resolution` is one the source recorded no contract for — a
  board a pair never played, or one the director adjusted. It is kept, because
  the pairs and the fact of the non-result are themselves part of the record.
  """

  north_south: PairIdentity
  east_west: PairIdentity
  # None when the source recorded no contract for the row.
  resolution: Resolution | None = None
  # Signed from North-South's perspective, where the matchpoints below stay per
  # side; travellers.md `#traveller-model` says why the two differ. None when
  # the source printed no score — the same rows `resolution` is None for.
  score: int | None = None
  # None when the source printed no matchpoints for that side. Typically, a
  # board with no recorded result.
  north_south_matchpoints: float | None = None
  east_west_matchpoints: float | None = None
  # Only the ACBL surfaces have a column for the opening lead, and every capture
  # so far leaves it empty on every row, so in practice the lead stays
  # sheet-only. None means the source recorded none.
  opening_lead: Card | None = None
  # What could not be read from this row, and why. A field left None because its
  # source said nothing carries no issue; one left None because what the source
  # said was unreadable carries one.
  issues: tuple[Issue, ...] = ()


class TravellerBoard(FrozenModel):
  """One board of a traveller: what was dealt, what par was, and who did what.

  The deal and the double-dummy analysis are properties of the board, shared by
  every table that played it; the results are per table. Dealer and
  vulnerability are absent because both follow from the board number (see
  board_rotation) — what the parsers do with the values a source prints anyway
  is `notation.board_schedule_issues`.
  """

  number: int
  # None for a source that publishes results without hands.
  deal: Deal | None = None
  double_dummy_tricks: DoubleDummyTricks | None = None
  par: Par | None = None
  results: tuple[TravellerResult, ...] = ()
  # Board-level findings: what could not be read from the deal or the analysis,
  # and any contradiction between what the source printed and what the board
  # number fixes. Row-level findings sit on the row.
  issues: tuple[Issue, ...] = ()


class CaptureReference(FrozenModel):
  """Where a capture is filed, and where it was fetched from.

  Provenance only — neither handle takes part in working out which session a
  capture belongs to. That match reads the event and date out of the capture
  itself, because a handle carries neither reliably: the club's directors each
  file under their own naming, and an ACBL URL is an opaque game id.

  The two handles answer different questions and neither subsumes the other. The
  path always exists and always resolves to a file that can be parsed again; the
  URL exists only for a capture something fetched, and is the half nothing can
  recover once it is lost.
  """

  # The capture's path relative to the capture root, in POSIX spelling, so a
  # stored record still names its capture after the tree is moved or copied.
  path: str
  # The URL the capture was fetched from, as `capture_urls` recorded it at the
  # time. None for a capture saved by hand, which never had one — a guessed URL
  # would be worse than none, so nothing reconstructs one from the path.
  url: str | None = None


class Traveller(FrozenModel):
  """A whole captured session, from one source."""

  source: TravellerSource
  # The capture this traveller was parsed from.
  reference: CaptureReference
  event: str
  # None when the capture states no date of its own.
  date: datetime.date | None = None
  boards: tuple[TravellerBoard, ...] = ()
  # Findings about the capture as a whole rather than any one board — a page
  # holding no boards, or one whose event is not a pairs game at all.
  issues: tuple[Issue, ...] = ()
