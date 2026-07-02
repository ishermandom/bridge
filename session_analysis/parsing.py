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
import datetime
import re
from collections.abc import Sequence

from session_analysis import board_rotation, glyphs
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
from session_analysis.models import (
  Announcement,
  AuctionEntry,
  BoardNumber,
  Call,
  Card,
  Contract,
  Issue,
  Lead,
  Outcome,
  Passout,
  PlayedContract,
  Result,
  Schedule,
)
from session_analysis.notation import tricks_taken_from_sheet_result

# Issue codes this module raises. `Issue.code` stays a plain string until the
# parser and validation pass together settle the full set into an enum (see
# models.md); these are the parser's contribution to that set.
_UNPARSEABLE_CALL = 'unparseable_call'
_UNPARSEABLE_CONTRACT = 'unparseable_contract'
_UNPARSEABLE_LEAD = 'unparseable_lead'
_UNREADABLE_BOARD_NUMBER = 'unreadable_board_number'
_UNREADABLE_DATE = 'unreadable_date'
_MISPLACED_ALERT = 'misplaced_alert'

# The dash glyphs (see glyphs.DASHES), regex-escaped for embedding in a
# character class: a result's minus and a passout's strike-through may each be
# written as any of them.
_DASHES = re.escape(glyphs.DASHES)

# Named regex components for the bid and contract cells. Decomposing the
# patterns this way keeps each assembled pattern readable — the intent lives in
# the component's name, not in a comment decoding the syntax. `\s*` seams absorb
# the sheet's inconsistent spacing; a result carries its own sign, a plus or any
# dash. `(?P<name>…)` groups let the extraction sites read by name.
_LEVEL = r'(?P<level>[1-7])'
_STRAIN = r'(?P<strain>NT|[CDHSN])'  # notrump as `N` or `NT`; see below
_PENALTY = r'(?P<penalty>[*xX]{1,2})?'  # one mark doubled, two redoubled
_DECLARER = r'(?P<declarer>[NESW])'
_RESULT = rf'(?P<result>[+{_DASHES}]\d+)'
_SEAM = r'\s*'

# The bid glyphs of a call: a level and a strain. Any trailing `!` alert and
# `_`/`^` announcement are stripped before this is matched.
_BID_PATTERN = re.compile(_LEVEL + _STRAIN)

# A whole contract cell: `<level><strain>[penalty]<declarer><result>`. The
# penalty sits before the declarer.
_CONTRACT_PATTERN = re.compile(
  _LEVEL
  + _SEAM
  + _STRAIN
  + _SEAM
  + _PENALTY
  + _SEAM
  + _DECLARER
  + _SEAM
  + _RESULT
)

# A board number: a positive integer, ASCII, no leading zero. The leading
# `[1-9]` rules out `0` and a leading-zero misread in one stroke; nothing bounds
# it above (sessions run past the 16-board cycle the schedule repeats on).
_BOARD_NUMBER_PATTERN = re.compile(r'[1-9][0-9]*')

# The header date. The vision model is expected to transcribe it as numeric
# month/day (`6/29`), normalizing whatever the human wrote ('June 9th', `6.23`);
# see models.md. The year is absent on the sheet and inferred by the parser.
# Each part is one or two ASCII digits.
_HEADER_DATE_MONTH = r'(?P<month>[0-9]{1,2})'
_HEADER_DATE_DAY = r'(?P<day>[0-9]{1,2})'
_HEADER_DATE_PATTERN = re.compile(_HEADER_DATE_MONTH + '/' + _HEADER_DATE_DAY)

# A card's rank and suit — the plain card glyphs, nothing lead-specific. The ten
# is written `10` or the enum's own `T`; the `10` alternative leads so it wins
# over a bare `1`.
_CARD_RANK = r'(?P<rank>10|[2-9TJQKA])'
_CARD_SUIT = r'(?P<suit>[CDHS])'

# The opening-lead cell: a card written rank-then-suit, with an optional `o` for
# the 'of' spoken between them — `9oH` and `9H` both mean the nine of hearts.
_LEAD_OF = r'[oO]?'
_LEAD_PATTERN = re.compile(_CARD_RANK + _LEAD_OF + _CARD_SUIT)

# A struck-through cell: a run of any dash glyph. The other passout form — the
# word 'pass' in any wording ('PASS', 'ALL PASS') — is a substring test, not a
# pattern.
_STRUCK_THROUGH_PATTERN = re.compile(rf'[{_DASHES}]+')

# The two halves of a notrump-range announcement, each tagged by its marker so
# order does not matter: `^` is the superscript floor (an optional `+` marks 'a
# good N'), `_` the subscript ceiling. The vision model may transcribe them in
# either order (`^0_2` or `_2^0`); both mean the same range. Each digit is a
# teens value with the leading `1` implied (`^0` is 10, `_7` is 17).
_NOTRUMP_FLOOR_PATTERN = re.compile(r'\^(?P<floor>\d)(?P<soft>\+?)')
_NOTRUMP_CEILING_PATTERN = re.compile(r'_(?P<ceiling>\d)')

# Notrump ranges are written as their ones digit with the tens `1` implied.
_TEENS_BASE = 10

# Two strain letters collide with seat letters — `N` (notrump vs. North) and `S`
# (spades vs. South) — so a letter alone is ambiguous. The bid and contract
# patterns resolve each by position (strain slot vs. declarer slot). This
# single-letter map backs both the strain slot and the artificial-suit
# announcement; `_strain_from_glyphs` adds the `NT` spelling on top of it.
_STRAIN_BY_LETTER = {
  'C': Strain.CLUBS,
  'D': Strain.DIAMONDS,
  'H': Strain.HEARTS,
  'S': Strain.SPADES,
  'N': Strain.NOTRUMP,
}

# Card ranks keyed by their sheet glyph. The enum values cover every rank (the
# ten as `T`); the sheet also writes the ten as `10`, mapped in alongside.
_RANK_BY_GLYPH = {rank.value: rank for rank in Rank} | {'10': Rank.TEN}


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
    # Opening the span before reading the flag lets a chunk that both opens and
    # closes the box (`[2N]`) still count as inside it.
    if chunk.startswith('['):
      is_in_box = True
    flagged_for_discussion = is_in_box
    core = chunk.strip('[]')
    # A bracket written with surrounding space arrives as a bare `[` or `]`
    # chunk; it toggles the span but is not itself a call.
    if core:
      entries.append(_parse_auction_token(core, flagged_for_discussion))
    if chunk.endswith(']'):
      is_in_box = False
  return tuple(entries)


def parse_contract_cell(cell: str) -> Outcome:
  """Parse a contract cell into its `Outcome` envelope.

  The one cell encodes the final contract, its penalty, the declarer, and the
  result together; they share the raw text and issue list. A cell whose text
  contains 'pass' in any wording, or a struck-through cell, is an explicit
  passout. Anything else that doesn't parse yields a null resolution plus an
  `unparseable_contract` issue — the board is still stored (nothing is garbage).
  See models.md (Contract parsing).
  """
  text = cell.strip()

  # 'PASS' / 'ALL PASS' anywhere in the cell, or a run of dashes struck through
  # it, both mean the board was passed out.
  if 'pass' in text.lower() or _STRUCK_THROUGH_PATTERN.fullmatch(text):
    return Outcome(raw=cell, resolution=Passout())

  match = _CONTRACT_PATTERN.fullmatch(text)
  if not match:
    issue = Issue(
      code=_UNPARSEABLE_CONTRACT,
      severity=IssueSeverity.HIGH,
      message=f'could not parse contract cell: {cell!r}',
    )
    return Outcome(raw=cell, issues=(issue,))

  contract = Contract(
    level=int(match.group('level')),
    strain=_strain_from_glyphs(match.group('strain')),
    declarer=Direction(match.group('declarer')),
    penalty=_penalty_from_marks(match.group('penalty')),
  )
  # The result normalizer needs the level to convert a `-N` set; the regex has
  # already constrained the token to a `±N` form, so it cannot raise here.
  result = Result(
    tricks_taken=tricks_taken_from_sheet_result(
      match.group('result'), contract.level
    )
  )
  return Outcome(
    raw=cell, resolution=PlayedContract(contract=contract, result=result)
  )


def parse_lead(cell: str) -> Lead:
  """Parse an opening-lead cell into its `Lead` envelope.

  The cell is a card: a rank then a suit, with an optional `o` for the spoken
  'of' between them (`9oH` and `9H` both mean the nine of hearts). The ten may
  be written `10` or `T`. A cell that doesn't match yields a null card plus an
  `unparseable_lead` issue — the board is still stored (nothing is garbage). A
  board with no recorded lead is the assembler's concern, kept as a null
  `opening_lead`; this parser assumes a lead was written. See models.md (Lead).
  """
  text = cell.strip()

  match = _LEAD_PATTERN.fullmatch(text)
  if not match:
    issue = Issue(
      code=_UNPARSEABLE_LEAD,
      severity=IssueSeverity.MEDIUM,
      message=f'could not parse opening lead: {cell!r}',
    )
    return Lead(raw=cell, issues=(issue,))

  card = Card(
    rank=_RANK_BY_GLYPH[match.group('rank')],
    suit=Suit(match.group('suit')),
  )
  return Lead(raw=cell, card=card)


def parse_board_number(cell: str) -> BoardNumber:
  """Parse a board-number cell into its `BoardNumber` envelope.

  The number fixes the deal: under the standard 16-board cycle it determines the
  dealer and vulnerability, which `board_rotation` computes into the `Schedule`
  bundled here — the envelope's parsed value is present only when the number was
  read and valid. A non-numeric or non-positive cell yields a null schedule plus
  an `unreadable_board_number` issue; the board is still stored and flagged for
  review (nothing is garbage). See models.md (BoardNumber, Schedule).
  """
  match = _BOARD_NUMBER_PATTERN.fullmatch(cell.strip())
  if not match:
    issue = Issue(
      code=_UNREADABLE_BOARD_NUMBER,
      severity=IssueSeverity.HIGH,
      message=f'could not read a board number from cell: {cell!r}',
    )
    return BoardNumber(raw=cell, issues=(issue,))

  number = int(match.group())
  schedule = Schedule(
    number=number,
    dealer=board_rotation.dealer_for_board(number),
    vulnerability=board_rotation.vulnerability_for_board(number),
  )
  return BoardNumber(raw=cell, schedule=schedule)


@dataclasses.dataclass(frozen=True)
class ParsedHeader:
  """The parsed session header: its date and any issues.

  These feed the session-level fields directly — `Session.date` and
  `Session.issues`. The header carries no envelope of its own, so a misread date
  is null with a session-level issue. `event` is absent here: it is the raw
  header text, stored verbatim and never parsed. Our pair identity is not read
  from the sheet at all — it is resolved from the travellers at reconciliation
  (see models.md, Session).
  """

  date: datetime.date | None
  issues: tuple[Issue, ...]


def parse_header(
  date_text: str, *, reference_date: datetime.date
) -> ParsedHeader:
  """Parse the session header's date into its canonical value.

  The sheet writes the date as month/day with no year (`6/29`); the year is
  inferred against `reference_date` — the day of the scan — on the assumption
  that a scanned sheet is at most a few months old and never from the future, so
  a December sheet scanned in January reads as the prior year. The date is null
  with a session-level issue when it can't be read, never a failure (nothing is
  garbage). See models.md (Session).
  """
  date = _date_from_header(date_text, reference_date)
  if date:
    return ParsedHeader(date=date, issues=())

  issue = Issue(
    code=_UNREADABLE_DATE,
    severity=IssueSeverity.MEDIUM,
    message=f'could not read a date from header: {date_text!r}',
  )
  return ParsedHeader(date=None, issues=(issue,))


def _date_from_header(
  text: str, reference_date: datetime.date
) -> datetime.date | None:
  """Return the date a header cell holds, or None when it can't be read.

  The sheet writes month/day with no year; the year is inferred against
  `reference_date`. A scanned sheet is assumed to be at most a few months old
  and never from the future, so the month/day is read as its most recent past
  occurrence: this year's if it has already come, otherwise last year's (a
  December sheet scanned in January). An out-of-range month or day (a misread
  `13/40`, or Feb 30) fails date construction and returns None.
  """
  match = _HEADER_DATE_PATTERN.fullmatch(text.strip())
  if not match:
    return None
  month, day = int(match.group('month')), int(match.group('day'))

  # This year's occurrence if it has already arrived, else last year's. Since
  # occurrences sit a full year apart and a sheet is only ever months old, this
  # choice is unambiguous.
  for year in (reference_date.year, reference_date.year - 1):
    try:
      candidate = datetime.date(year, month, day)
    except ValueError:
      # Out of range for this year (a misread `13/40`, or Feb 29 in a non-leap
      # year); try the prior year before giving up.
      continue
    if candidate <= reference_date:
      return candidate
  return None


def _strain_from_glyphs(glyphs_text: str) -> Strain:
  """Map a bid/contract strain glyph to its `Strain` (notrump is `N`/`NT`)."""
  if glyphs_text == 'NT':
    return Strain.NOTRUMP
  return _STRAIN_BY_LETTER[glyphs_text]


def _penalty_from_marks(marks: str | None) -> Penalty:
  """Map a contract's penalty marks to a `Penalty`.

  The mark is `*` or `x`/`X`; only the count matters — one is doubled, two is
  redoubled. Absent marks are no penalty.
  """
  if not marks:
    return Penalty.NONE
  return Penalty.DOUBLED if len(marks) == 1 else Penalty.REDOUBLED


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

  The core is a bid (`2H`, with an optional trailing `!` alert and `_`/`^`
  announcement), or a standalone pass (`p`), double (`*`/`x`), or redouble
  (`**`/`xx`). A bid whose glyphs don't match yields no call and an
  `unparseable_call` issue.
  """
  # An alert `!` is only valid at the very end of a call. A `!` anywhere else
  # isn't a real alert mark, so flag it for a human and strip it before a
  # best-effort parse of what remains.
  alerted = core.endswith('!')
  body = core[:-1] if alerted else core
  issues: tuple[Issue, ...] = ()
  if '!' in body:
    issues = (
      Issue(
        code=_MISPLACED_ALERT,
        severity=IssueSeverity.MEDIUM,
        message=f'alert mark not at end of call: {core!r}',
      ),
    )
    body = body.replace('!', '')

  if body in ('p', 'P'):
    return _ParsedCore(Call(kind=CallKind.PASS), alerted, issues)
  if body in ('*', 'x', 'X'):
    return _ParsedCore(Call(kind=CallKind.DOUBLE), alerted, issues)
  if body in ('**', 'xx', 'XX'):
    return _ParsedCore(Call(kind=CallKind.REDOUBLE), alerted, issues)

  parsed = _parse_bid(body, alerted)
  return _ParsedCore(parsed.call, alerted, issues + parsed.issues)


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

  strain = _strain_from_glyphs(match.group('strain'))
  announcement = (
    _parse_announcement(announcement_text, strain)
    if announcement_text
    else None
  )
  call = Call(
    kind=CallKind.BID,
    level=int(match.group('level')),
    strain=strain,
    announcement=announcement,
  )
  return _ParsedCore(call, alerted, ())


def _parse_announcement(text: str, bid_strain: Strain) -> Announcement:
  """Interpret a bid's announcement markup into an `Announcement`.

  `text` still carries its `_`/`^` markers. A superscript is a notrump range; a
  subscript strain letter is an artificial suit shown; a subscript digit is a
  minimum length in the bid's own suit; `SF`/`F` are semi-forcing/forcing.
  Anything else unrecognized degrades to `AnnouncementType.OTHER` with the raw
  text preserved, so a novel form never fails. See models.md (Announcement
  decoding).
  """
  # A superscript means a notrump range; detect it first, since its subscript
  # ceiling would otherwise look like the bare min-length subscript below.
  if '^' in text:
    return _parse_notrump_range(text)

  # The remaining forms are a single subscript; drop only its marker, so `_S`
  # reads as `S`, matching how the range above keeps its markers in `raw`.
  body = text.removeprefix('_')

  if body in _STRAIN_BY_LETTER:
    return Announcement(
      raw=body,
      type=AnnouncementType.ARTIFICIAL_SUIT,
      shown_strain=_STRAIN_BY_LETTER[body],
    )
  if body == 'SF':
    return Announcement(raw=body, type=AnnouncementType.SEMI_FORCING)
  if body == 'F':
    return Announcement(raw=body, type=AnnouncementType.FORCING)
  # A digit is a minimum length in the bid's own suit; notrump has no suit for
  # the length to describe, so such a mark degrades to `other`.
  if body.isdigit() and bid_strain != Strain.NOTRUMP:
    return Announcement(
      raw=body,
      type=AnnouncementType.MIN_SUIT_LENGTH,
      suit=Suit(bid_strain.value),
      minimum_length=int(body),
    )
  return Announcement(raw=body, type=AnnouncementType.OTHER)


def _parse_notrump_range(text: str) -> Announcement:
  """Decode a notrump-range announcement (`^0_2` is 10-12) into `nt_range`.

  The superscript is the minimum and the subscript the maximum, written in
  either order (`^0_2` or `_2^0` are the same range). A `+` on the minimum ('a
  good 14') sets `minimum_points_is_soft`, a nuance the point floor alone can't
  hold. A superscript form missing a half, or carrying extra glyphs, degrades to
  `other`, raw preserved.
  """
  floor = _NOTRUMP_FLOOR_PATTERN.search(text)
  ceiling = _NOTRUMP_CEILING_PATTERN.search(text)
  # Both halves must be present and together account for the whole text; a form
  # missing a half or carrying stray glyphs is a novel form, not a range.
  if not floor or not ceiling:
    return Announcement(raw=text, type=AnnouncementType.OTHER)
  matched_length = len(floor.group()) + len(ceiling.group())
  if matched_length != len(text):
    return Announcement(raw=text, type=AnnouncementType.OTHER)

  return Announcement(
    raw=text,
    type=AnnouncementType.NT_RANGE,
    minimum_points=_TEENS_BASE + int(floor.group('floor')),
    minimum_points_is_soft=bool(floor.group('soft')),
    maximum_points=_TEENS_BASE + int(ceiling.group('ceiling')),
  )
