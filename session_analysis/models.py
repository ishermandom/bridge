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
)


class Issue(pydantic.BaseModel):
  """A review flag: one item worth a human's attention on a board."""

  code: str
  severity: IssueSeverity
  message: str
  location: str | None = None


class Announcement(pydantic.BaseModel):
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
  maximum_points: int | None = None


class Card(pydantic.BaseModel):
  """A single card, whole only when both rank and suit were understood."""

  rank: Rank
  suit: Suit


class Contract(pydantic.BaseModel):
  """A final contract, present only when it was fully understood."""

  level: int
  strain: Strain
  declarer: Direction
  penalty: Penalty


class Result(pydantic.BaseModel):
  """A contract's result, as the canonical trick count."""

  tricks_taken: int


class Call(pydantic.BaseModel):
  """An understood call: a bid, pass, double, or redouble.

  `level` and `strain` are set for bids and absent for the other kinds — a
  kind-driven distinction, not a parse failure. Parse failure is the wrapping
  `AuctionEntry.call` being null.
  """

  kind: CallKind
  level: int | None = None
  strain: Strain | None = None
  announcement: Announcement | None = None


class AuctionEntry(pydantic.BaseModel):
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
  issues: list[Issue] = pydantic.Field(default_factory=list)


class Lead(pydantic.BaseModel):
  """The opening lead as written: transcription, issues, and the parsed card."""

  raw: str
  card: Card | None = None
  issues: list[Issue] = pydantic.Field(default_factory=list)


class PlayedContract(pydantic.BaseModel):
  """A contract that was played, with the result it produced."""

  kind: Literal['played'] = 'played'
  contract: Contract
  result: Result


class Passout(pydantic.BaseModel):
  """A passed-out board: every player passed, so no contract was played."""

  kind: Literal['passout'] = 'passout'


# What a board's auction resolved to, tagged by `kind` so a played contract and
# a passout stay distinct in the stored JSON as well as in the types.
Resolution = Annotated[
  PlayedContract | Passout, pydantic.Field(discriminator='kind')
]


class Outcome(pydantic.BaseModel):
  """A board's contract cell: what its auction resolved to.

  `resolution` is the understood outcome — a `PlayedContract` or a `Passout` —
  and is null only when the cell couldn't be parsed. So a passout is an explicit
  understood state, kept distinct from an unparsed cell.
  """

  raw: str
  resolution: Resolution | None = None
  issues: list[Issue] = pydantic.Field(default_factory=list)
