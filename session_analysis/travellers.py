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
"""

import datetime
import enum
from collections.abc import Mapping

from session_analysis.enums import Direction, Strain
from session_analysis.frozen_model import FrozenModel
from session_analysis.models import Card, Deal, PairIdentity, Resolution


class TravellerSource(enum.StrEnum):
  """Where a traveller was captured from.

  The two ACBL surfaces are named apart because they publish different markup
  and cover different events, not because the records differ once parsed.
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
  # side; travellers.md (Traveller data model) says why the two differ. None
  # when the source printed no score — the same rows `resolution` is None for.
  score: int | None = None
  # None when the source printed no matchpoints for that side. Typically, a
  # board with no recorded result.
  north_south_matchpoints: float | None = None
  east_west_matchpoints: float | None = None
  # Only the ACBL surfaces have a column for the opening lead, and every capture
  # so far leaves it empty on every row, so in practice the lead stays
  # sheet-only. None means the source recorded none.
  opening_lead: Card | None = None


class TravellerBoard(FrozenModel):
  """One board of a traveller: what was dealt, what par was, and who did what.

  The deal and the double-dummy analysis are properties of the board, shared by
  every table that played it; the results are per table. Dealer and
  vulnerability are absent because both follow from the board number (see
  board_rotation) — what the parsers do with the values a source prints anyway
  is `traveller_notation.check_board_schedule`.
  """

  number: int
  # None for a source that publishes results without hands.
  deal: Deal | None = None
  double_dummy_tricks: DoubleDummyTricks | None = None
  par: Par | None = None
  results: tuple[TravellerResult, ...] = ()


class Traveller(FrozenModel):
  """A whole captured session, from one source."""

  source: TravellerSource
  # Whatever handle identifies the capture this was parsed from, so a stored
  # record can be traced back to it — its saved path, or the URL it was fetched
  # from. Provenance only: a capture is matched to a session by the event and
  # date parsed out of its contents, never by its path or URL, because neither
  # is reliable across the directors who publish them. Which handle to keep, or
  # whether to keep both, is the storage task's decision.
  reference: str
  event: str
  # None when the capture states no date of its own.
  date: datetime.date | None = None
  boards: tuple[TravellerBoard, ...] = ()
