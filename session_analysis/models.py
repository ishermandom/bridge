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
parse explicit: a `None` parsed value means the token couldn't be understood as
a whole, rather than each field being independently absent. Content validation
(bridge legality, ranges) is the validation pass's job, not these models'.
"""

import datetime
from collections.abc import Mapping
from typing import Annotated, Literal

import pydantic

from session_analysis.enums import (
  AnnouncementType,
  CallKind,
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Side,
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


class Hand(FrozenModel):
  """The cards one player held on a board.

  Thirteen of them, in a well-formed deal — but that is not a constraint here,
  for the reason `Deal` gives: a source printing a malformed hand is surfaced at
  reconciliation rather than refused at parse time.
  """

  cards: tuple[Card, ...]


class Deal(FrozenModel):
  """A board's four hands, one per seat.

  Traveller-sourced: the sheet records nothing about the deal, so a deal is
  filled at reconciliation or not at all. Well-formedness — fifty-two distinct
  cards, thirteen to a hand — is a reconciliation-time check rather than a
  constraint here, so a source that prints a malformed deal still parses and is
  surfaced rather than rejected.
  """

  hands: Mapping[Direction, Hand]


class PairIdentity(FrozenModel):
  """Who a traveller says a pair was, on one board.

  A per-board identity, not a session-wide one. `number` and `side` together
  name a pair on the row they were read from: a two-winner movement numbers its
  two directions separately, so the side is what tells pair 5 North-South from
  pair 5 East-West — but a one-winner movement sits one pair both ways over a
  session, and the same two players then surface under two identities. What is
  stable across a session is the players, not this.

  Traveller-sourced. The sheet does carry a pair number, but the vision model is
  told to disregard it (see models.md `#vision-output`): the traveller is
  authoritative for who sat where.
  """

  # A label rather than a quantity — nothing counts or orders it — so it keeps
  # the source's own spelling, which varies: `7` at one club, `A9` where the
  # section prefixes the number, `10` where two digits are needed.
  number: str
  side: Side
  # `None` when the event ran a single unnamed section.
  section: str | None = None
  # The two players, each written given name first — the order the Palo Alto
  # club and the sheets use, and the one ACBL's surname-first filing is turned
  # around into, so that two captures of a session compare on their names rather
  # than on their spelling of them. Sources differ in how much they give: ACBL
  # prints full names, the club's per-board rows only surnames — so the club
  # parsers recover full names from the standings recap the capture embeds,
  # keyed by `number` and `side`.
  names: tuple[str, ...] = ()


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
  `AuctionEntry.call` being `None`.
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
  flagged_for_discussion: bool = False
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
  and is `None` only when the cell couldn't be parsed. So a passout is an
  explicit understood state, kept distinct from an unparsed cell.
  """

  raw: str
  resolution: Resolution | None = None
  flagged_for_discussion: bool = False
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

  Follows the parse-envelope pattern — `raw` plus a parsed value that is `None`
  when the cell couldn't be understood. Here that value is `schedule`: a fully
  populated `Schedule` when the number was read and valid, or `None` when it was
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
  # Traveller-sourced; filled at reconciliation, `None` until then and for
  # no-traveller sessions.
  matchpoints: float | None = None
  notes: str | None = None
  issues: tuple[Issue, ...] = ()


class SheetImage(FrozenModel):
  """The scanned sheet a session was digitized from."""

  path: str
  content_hash: str


class CaptureReference(FrozenModel):
  """Where a traveller capture is filed, and where it was fetched from.

  Provenance only — neither handle takes part in working out which session a
  capture belongs to. That match reads the event and date out of the capture
  itself, because a handle carries neither reliably: the club's directors each
  file under their own naming, and an ACBL URL is an opaque game id.

  The two handles answer different questions and neither subsumes the other. The
  path always exists and always resolves to a file that can be parsed again; the
  URL exists only for a capture something fetched, and is the half nothing can
  recover once it is lost.

  It sits here beside `SheetImage` rather than in travellers.py because both the
  stored traveller and the sheet's `Source` name a capture this way, and
  travellers.py already depends on this module.
  """

  # The capture's path relative to the capture root, in POSIX spelling, so a
  # stored record still names its capture after the tree is moved or copied.
  path: str
  # The URL the capture was fetched from, as `capture_urls` recorded it at the
  # time. None for a capture saved by hand, which never had one — a guessed URL
  # would be worse than none, so nothing reconstructs one from the path.
  url: str | None = None


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
  """A whole digitized session: its footer, provenance, and boards.

  Like the rest of the models, the parsed footer date never hard-fails: a value
  the parser couldn't read is `None` with an issue, not a construction error, so
  a session is always stored and reviewable (nothing is garbage). `event` and
  `source` are the always-present exceptions — `event` is the raw footer
  transcription, `source` is file provenance, neither a parse that can fail.

  Our own pair identity is deliberately not read from the sheet: a pair is
  identified by number and direction (sometimes a section too), not a bare
  number, and that identity is recovered far more directly from the travellers.
  It is resolved at reconciliation, alongside the traveller type that phase
  defines, and is simply absent for a no-traveller session.
  """

  # Stable identifier derived from event and date (e.g. `pabc-mon-2026-06-29`);
  # the filename and the reconciliation join. `None` until ingest assigns it,
  # downstream of parsing and review.
  session_key: str | None = None
  event: str
  # Parsed from the footer, or `None` with an issue when unreadable.
  date: datetime.date | None = None
  source: Source
  boards: tuple[Board, ...] = ()
  # Session-level issues, such as an unreadable date; board- and token-level
  # issues live on the board and its envelopes.
  issues: tuple[Issue, ...] = ()
