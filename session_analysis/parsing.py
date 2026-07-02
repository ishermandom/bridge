# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Turn the vision model's flat strings into the canonical parsed model.

This is the project's interpretation layer: all bridge convention lives here,
not in the vision model (which only transcribes) and not in the models (which
only hold and serialize). It never raises — an unparseable token yields a null
parsed value inside its envelope plus an `Issue`, so nothing is ever dropped.
See models.md (Parsing).
"""

import dataclasses
import re
from collections.abc import Sequence

from session_analysis import glyphs
from session_analysis.enums import (
  AnnouncementType,
  CallKind,
  Direction,
  IssueSeverity,
  Penalty,
  Strain,
  Suit,
)
from session_analysis.models import (
  Announcement,
  AuctionEntry,
  Call,
  Contract,
  Issue,
  Outcome,
  Passout,
  PlayedContract,
  Result,
)
from session_analysis.notation import tricks_taken_from_sheet_result

# Issue codes this module raises. `Issue.code` stays a plain string until the
# parser and validation pass together settle the full set into an enum (see
# models.md); these are the parser's contribution to that set.
_UNPARSEABLE_CALL = 'unparseable_call'
_UNPARSEABLE_CONTRACT = 'unparseable_contract'

# The bid glyphs of a call: a level 1-7 and a strain (`N` is notrump). Any
# trailing `!` and `_`/`^` announcement are stripped before this is matched.
_BID_PATTERN = re.compile(r'([1-7])([CDHSN])')

# The dash glyphs (see glyphs.DASHES), regex-escaped for embedding in a
# character class: a result's minus and a passout's strike-through may each be
# written as any of them.
_DASHES = re.escape(glyphs.DASHES)

# A whole contract cell: `<level><strain>[*|**]<declarer><result>`, with spacing
# on the sheet inconsistent, so every seam tolerates optional whitespace. The
# `*`/`**` penalty sits before the declarer; the result carries its own sign, a
# plus or any dash.
_CONTRACT_PATTERN = re.compile(
  rf'([1-7])\s*([CDHSN])\s*(\*{{1,2}})?\s*([NESW])\s*([+{_DASHES}]\d+)'
)

# A passed-out cell: the explicit word, or a run of dashes struck through it.
_PASSOUT_PATTERN = re.compile(rf'PASSOUT|[{_DASHES}]+', re.IGNORECASE)

# A notrump-range announcement: a superscript minimum and subscript maximum,
# each a teens value with the leading `1` implied (`^0_2` is 10-12). An optional
# `+` on the minimum ('a good 14') is a nuance the point range can't hold; it
# survives only in the raw text.
_NOTRUMP_RANGE_PATTERN = re.compile(r'\^(\d)\+?_(\d)')

# Notrump ranges are written as their ones digit with the tens `1` implied.
_TEENS_BASE = 10

# `N` doubles as a strain (notrump) and a seat (North); context picks which.
_STRAIN_BY_LETTER = {
  'C': Strain.CLUBS,
  'D': Strain.DIAMONDS,
  'H': Strain.HEARTS,
  'S': Strain.SPADES,
  'N': Strain.NOTRUMP,
}

_PENALTY_BY_MARKS = {
  None: Penalty.NONE,
  '*': Penalty.DOUBLED,
  '**': Penalty.REDOUBLED,
}


def parse_auction(auction: str) -> Sequence[AuctionEntry]:
  """Parse an auction string into its per-token `AuctionEntry` envelopes.

  Tokenizing is not a plain split on spaces: a box `[ … ]` opens a to-discuss
  span that can cover several space-separated calls, so box state is tracked
  across tokens. A circle `( … )` wraps exactly one call. Both are stripped to
  booleans (`flagged_for_discussion`, `by_opponents`); the remaining call core
  is parsed into a `Call`, or kept as `raw` with an `unparseable_call` issue
  when it can't be understood. See models.md (Auction grammar).
  """
  entries: list[AuctionEntry] = []
  is_in_box = False
  for chunk in auction.split():
    opens_box = chunk.startswith('[')
    closes_box = chunk.endswith(']')
    # A box may span several chunks, so a chunk is inside the span if the box
    # was already open or opens on this chunk.
    flagged_for_discussion = is_in_box or opens_box
    core = chunk.strip('[]')
    # A bracket written with surrounding space arrives as a bare `[` or `]`
    # chunk; it toggles the span but is not itself a call.
    if core:
      entries.append(_parse_auction_token(core, flagged_for_discussion))
    if opens_box:
      is_in_box = True
    if closes_box:
      is_in_box = False
  return tuple(entries)


def parse_contract_cell(cell: str) -> Outcome:
  """Parse a contract cell into its `Outcome` envelope.

  The one cell encodes the final contract, its penalty, the declarer, and the
  result together; they share the raw text and issue list. `PASSOUT` or a
  struck-through cell is an explicit passout. Anything else that doesn't parse
  yields a null resolution plus an `unparseable_contract` issue — the board is
  still stored (nothing is garbage). See models.md (Contract parsing).
  """
  text = cell.strip()

  if _PASSOUT_PATTERN.fullmatch(text):
    return Outcome(raw=cell, resolution=Passout())

  match = _CONTRACT_PATTERN.fullmatch(text)
  if not match:
    issue = Issue(
      code=_UNPARSEABLE_CONTRACT,
      severity=IssueSeverity.HIGH,
      message=f'could not parse contract cell: {cell!r}',
    )
    return Outcome(raw=cell, issues=(issue,))

  level_text, strain_letter, penalty_marks, declarer_letter, result_token = (
    match.groups()
  )
  level = int(level_text)
  contract = Contract(
    level=level,
    strain=_STRAIN_BY_LETTER[strain_letter],
    declarer=Direction(declarer_letter),
    penalty=_PENALTY_BY_MARKS[penalty_marks],
  )
  # The result normalizer needs the level to convert a `-N` set; the regex has
  # already constrained the token to a `±N` form, so it cannot raise here.
  result = Result(
    tricks_taken=tricks_taken_from_sheet_result(result_token, level)
  )
  return Outcome(
    raw=cell, resolution=PlayedContract(contract=contract, result=result)
  )


@dataclasses.dataclass(frozen=True)
class _ParsedCore:
  """A parsed call core: the understood call, its alert flag, and any issues.

  `alerted` rides alongside `call` rather than inside it because the `!` belongs
  to the `AuctionEntry`, not the `Call` — it survives a content-parse failure.
  """

  call: Call | None
  alerted: bool
  issues: tuple[Issue, ...]


def _parse_auction_token(
  core: str, flagged_for_discussion: bool
) -> AuctionEntry:
  """Parse one auction token (box markup already stripped) into an entry.

  A wrapping circle marks a call by the opponents; the rest is the call core.
  `raw` keeps that core — the structural markup is already captured in the
  booleans, so it would only be redundant there.
  """
  by_opponents = core.startswith('(') and core.endswith(')')
  call_core = core.strip('()') if by_opponents else core

  parsed = _parse_call_core(call_core)
  return AuctionEntry(
    raw=call_core,
    by_opponents=by_opponents,
    alerted=parsed.alerted,
    flagged_for_discussion=flagged_for_discussion,
    call=parsed.call,
    issues=parsed.issues,
  )


def _parse_call_core(core: str) -> _ParsedCore:
  """Parse a call core (structural markup stripped) into a `Call`.

  The core is a bid (`2H`, with an optional `!` alert and `_`/`^` announcement),
  or a standalone pass (`p`), double (`*`), or redouble (`**`). A bid whose
  glyphs don't match `[1-7][CDHSN]` yields no call and an `unparseable_call`
  issue.
  """
  alerted = '!' in core
  core = core.replace('!', '')

  if core in ('p', 'P'):
    return _ParsedCore(Call(kind=CallKind.PASS), alerted, ())
  if core == '*':
    return _ParsedCore(Call(kind=CallKind.DOUBLE), alerted, ())
  if core == '**':
    return _ParsedCore(Call(kind=CallKind.REDOUBLE), alerted, ())

  return _parse_bid(core, alerted)


def _parse_bid(core: str, alerted: bool) -> _ParsedCore:
  """Parse a bid core (`2H`, `1N_SF`, `1N^0_2`) into a bid `Call`."""
  # The announcement, if any, begins at the first `_` or `^`; the bid glyphs
  # precede it.
  marker_positions = [core.index(mark) for mark in ('_', '^') if mark in core]
  announcement_start = min(marker_positions, default=len(core))
  bid_glyphs = core[:announcement_start]
  announcement_text = core[announcement_start:]

  match = _BID_PATTERN.fullmatch(bid_glyphs)
  if not match:
    issue = Issue(
      code=_UNPARSEABLE_CALL,
      severity=IssueSeverity.MEDIUM,
      message=f'could not parse call: {core!r}',
    )
    return _ParsedCore(None, alerted, (issue,))

  level, strain_letter = match.groups()
  strain = _STRAIN_BY_LETTER[strain_letter]
  announcement = (
    _parse_announcement(announcement_text, strain)
    if announcement_text
    else None
  )
  call = Call(
    kind=CallKind.BID,
    level=int(level),
    strain=strain,
    announcement=announcement,
  )
  return _ParsedCore(call, alerted, ())


def _parse_announcement(text: str, bid_strain: Strain) -> Announcement:
  """Interpret a bid's announcement markup into an `Announcement`.

  `text` still carries its `_`/`^` markers. A subscript strain letter is an
  artificial suit shown; a subscript digit is a minimum length in the bid's own
  suit; `SF`/`F` are semi-forcing/forcing; a superscript is a notrump range
  (`^0_2` is 10-12). Anything else unrecognized degrades to
  `AnnouncementType.OTHER` with the raw text preserved, so a novel form never
  fails. See models.md (Announcement decoding).
  """
  # Drop only the subscript marker: `_S` reads as `S`, while a superscript form
  # like `^0_2` keeps its markers, matching how each is written.
  raw = text.removeprefix('_')

  if '^' in raw:
    return _parse_notrump_range(raw)

  if raw in _STRAIN_BY_LETTER:
    return Announcement(
      raw=raw,
      type=AnnouncementType.ARTIFICIAL_SUIT,
      shown_strain=_STRAIN_BY_LETTER[raw],
    )
  if raw == 'SF':
    return Announcement(raw=raw, type=AnnouncementType.SEMI_FORCING)
  if raw == 'F':
    return Announcement(raw=raw, type=AnnouncementType.FORCING)
  # A digit is a minimum length in the bid's own suit; notrump has no suit for
  # the length to describe, so such a mark degrades to `other`.
  if raw.isdigit() and bid_strain != Strain.NOTRUMP:
    return Announcement(
      raw=raw,
      type=AnnouncementType.MIN_SUIT_LENGTH,
      suit=Suit(bid_strain.value),
      minimum_length=int(raw),
    )
  return Announcement(raw=raw, type=AnnouncementType.OTHER)


def _parse_notrump_range(raw: str) -> Announcement:
  """Decode a notrump-range announcement (`^0_2` is 10-12) into `nt_range`.

  The superscript is the minimum and the subscript the maximum, each a teens
  value with the leading `1` implied (`^0` is 10, `_7` is 17). A `+` on the
  minimum ('a good 14') is a nuance the point range can't hold, so it survives
  only in `raw`. A superscript form that doesn't fit this shape degrades to
  `other`, raw preserved.
  """
  match = _NOTRUMP_RANGE_PATTERN.fullmatch(raw)
  if not match:
    return Announcement(raw=raw, type=AnnouncementType.OTHER)

  minimum_digit, maximum_digit = match.groups()
  return Announcement(
    raw=raw,
    type=AnnouncementType.NT_RANGE,
    minimum_points=_TEENS_BASE + int(minimum_digit),
    maximum_points=_TEENS_BASE + int(maximum_digit),
  )
