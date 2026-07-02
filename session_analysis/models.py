# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The canonical, structured shape of a digitized session, as stored.

This is the parser's output: the fully structured record that gets validated,
reviewed, corrected, and saved as JSON. It is distinct from the vision model's
response, which is flat and string-valued (the auction is a single string) — the
parser turns that into these types. So these models (de)serialize to and from
the JSON store, not to the vision model.

Each written token is kept in a small envelope — its raw transcription, any
marks, its issues, and the parsed value when the token could be understood (e.g.
`AuctionEntry` around `Call`). The envelope makes the all-or-nothing nature of a
parse explicit: a null parsed value means the token couldn't be understood as a
whole, rather than each field being independently absent. Content validation
(bridge legality, ranges) is the validation pass's job, not these models'.
"""

import datetime
from typing import Annotated, Literal

import pydantic

from session_analysis.enums import (
  AnnouncementType,
  CallKind,
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Strain,
  Suit,
  Vulnerability,
)
from session_analysis.frozen_model import FrozenModel


class Issue(FrozenModel):
  """A review flag: one item worth a human's attention on a board."""

  code: str
  severity: IssueSeverity
  message: str
  location: str | None = None


class Announcement(FrozenModel):
  """The meaning announced for a bid.

  A tagged value: `type` selects the meaning and the matching payload fields
  carry it, while `raw` preserves the original text. An unrecognized form
  degrades to `AnnouncementType.OTHER`, carried by `raw` alone, so a novel
  announcement never fails — it needs no parse envelope of its own.
  """

  raw: str
  type: AnnouncementType
  shown_strain: Strain | None = None
  suit: Suit | None = None
  minimum_length: int | None = None
  minimum_points: int | None = None
  # True for 'a good 14' (`^N+`): the floor is `minimum_points`, but the hand
  # runs a shade stronger than the bare number — a nuance the number can't hold.
  minimum_points_is_soft: bool = False
  maximum_points: int | None = None


class Card(FrozenModel):
  """A single card, whole only when both rank and suit were understood."""

  rank: Rank
  suit: Suit


class Contract(FrozenModel):
  """A final contract, present only when it was fully understood."""

  level: int
  strain: Strain
  declarer: Direction
  penalty: Penalty


class Result(FrozenModel):
  """A contract's result, as the canonical trick count."""

  tricks_taken: int


class Call(FrozenModel):
  """An understood call: a bid, pass, double, or redouble.

  `level` and `strain` are set for bids and absent for the other kinds — a
  kind-driven distinction, not a parse failure. Parse failure is the wrapping
  `AuctionEntry.call` being null.
  """

  kind: CallKind
  level: int | None = None
  strain: Strain | None = None
  announcement: Announcement | None = None


class AuctionEntry(FrozenModel):
  """One written token of the auction.

  Carries the always-available transcription and marks, plus the understood
  `call` when the token could be parsed. Marks live here rather than on `Call`
  because they survive a content-parse failure: a circled but unreadable token
  is still known to be the opponents'.
  """

  raw: str
  by_opponents: bool = False
  alerted: bool = False
  flagged_for_discussion: bool = False
  call: Call | None = None
  issues: tuple[Issue, ...] = ()


class Lead(FrozenModel):
  """The opening lead as written: transcription, issues, and the parsed card."""

  raw: str
  card: Card | None = None
  issues: tuple[Issue, ...] = ()


class PlayedContract(FrozenModel):
  """A contract that was played, with the result it produced."""

  kind: Literal['played'] = 'played'
  contract: Contract
  result: Result


class Passout(FrozenModel):
  """A passed-out board: every player passed, so no contract was played."""

  kind: Literal['passout'] = 'passout'


# What a board's auction resolved to, tagged by `kind` so a played contract and
# a passout stay distinct in the stored JSON as well as in the types.
Resolution = Annotated[
  PlayedContract | Passout, pydantic.Field(discriminator='kind')
]


class Outcome(FrozenModel):
  """A board's contract cell: what its auction resolved to.

  `resolution` is the understood outcome — a `PlayedContract` or a `Passout` —
  and is null only when the cell couldn't be parsed. So a passout is an explicit
  understood state, kept distinct from an unparsed cell.
  """

  raw: str
  resolution: Resolution | None = None
  issues: tuple[Issue, ...] = ()


class Schedule(FrozenModel):
  """A resolved board number and the deal parameters it fixes.

  The board number determines the dealer and vulnerability under the standard
  16-board cycle (see board_rotation). This bundles the parsed number with that
  derived pair as one all-or-nothing unit: it exists only when the number was
  read and resolved, so every field is present together — there is no partially
  known board. The parser builds it, computing dealer and vulnerability; the
  models derive nothing.
  """

  number: int
  dealer: Direction
  vulnerability: Vulnerability


class BoardNumber(FrozenModel):
  """The board-number cell envelope: its transcription and resolved schedule.

  Follows the parse-envelope pattern — `raw` plus a parsed value that is null
  when the cell couldn't be understood. Here that value is `schedule`: a fully
  populated `Schedule` when the number was read and valid, or null when it was
  unreadable or invalid. The board is stored and flagged for review either way —
  an unreadable number is a review item, not a reason to drop the board (nothing
  is garbage).
  """

  raw: str
  schedule: Schedule | None = None
  issues: tuple[Issue, ...] = ()


class Board(FrozenModel):
  """One board's fully parsed record: its number, auction, lead, and outcome.

  Groups the board's envelopes alongside its board-level context. The `number`
  envelope carries the board number and the dealer and vulnerability it fixes;
  `auction`, `opening_lead`, and `outcome` are the play; the rest are
  reconciliation and review fields.
  """

  number: BoardNumber
  flagged_for_review: bool = False
  auction: tuple[AuctionEntry, ...] = ()
  opening_lead: Lead | None = None
  outcome: Outcome | None = None
  # Traveller-sourced; filled at reconciliation, null until then and for
  # no-traveller sessions.
  matchpoints: float | None = None
  notes: str | None = None
  issues: tuple[Issue, ...] = ()


class SheetImage(FrozenModel):
  """The scanned sheet a session was digitized from."""

  path: str
  content_hash: str


class Source(FrozenModel):
  """Provenance for a digitized session: its image and travellers consulted.

  `travellers` records which travellers the reconciliation pass consulted; it is
  empty until then and for no-traveller sessions.
  """

  image: SheetImage
  # TODO: reconciliation will replace these path/URL references with a richer
  # traveller type once that phase defines one.
  travellers: tuple[str, ...] = ()


class Session(FrozenModel):
  """A whole digitized session: its header, provenance, and boards.

  Like the rest of the models, the parsed header date never hard-fails: a value
  the parser couldn't read is null with an issue, not a construction error, so a
  session is always stored and reviewable (nothing is garbage). `event` and
  `source` are the always-present exceptions — `event` is the raw header
  transcription, `source` is file provenance, neither a parse that can fail.

  Our own pair identity is deliberately not read from the sheet: a pair is
  identified by number and direction (sometimes a section too), not a bare
  number, and that identity is recovered far more directly from the travellers.
  It is resolved at reconciliation, alongside the traveller type that phase
  defines, and is simply absent for a no-traveller session.
  """

  # Stable identifier derived from event and date (e.g. `pabc-mon-2026-06-29`);
  # the filename and the reconciliation join. Null until ingest assigns it,
  # downstream of parsing and review.
  session_key: str | None = None
  event: str
  # Parsed from the header, or null with an issue when unreadable.
  date: datetime.date | None = None
  source: Source
  boards: tuple[Board, ...] = ()
  # Session-level issues, such as an unreadable date; board- and token-level
  # issues live on the board and its envelopes.
  issues: tuple[Issue, ...] = ()
