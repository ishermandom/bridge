# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read an ACBL club-game result page into a traveller.

A club game's page at `my.acbl.org/club-results/details/...` renders from a JSON
blob the page carries with it, assigned to a `data` variable in an inline
script. That blob is the parse target rather than the rendered markup: the page
builds its markup out of the blob, and that markup spells every suit as a glyph
and scatters a board across nested elements, where the blob holds the same facts
in plain text. The blob also survives a browser's own "save page", so a capture
saved by hand reads the same as one the fetcher retrieves.

Not every club game publishes a traveller. A team game's page carries match
results and no per-board rows at all, so it has nothing this parser can return —
an absence reported as an issue rather than passed off as an empty traveller.
"""

import dataclasses
import datetime
import json
import re
from collections.abc import Mapping, Sequence

from session_analysis import acbl_notation, issue_reporting, notation
from session_analysis.enums import Direction, IssueSeverity, Side
from session_analysis.models import (
  Contract,
  Deal,
  Hand,
  Issue,
  PairIdentity,
  Passout,
  PlayedContract,
  Resolution,
  Result,
)
from session_analysis.travellers import (
  DoubleDummyTricks,
  Par,
  Traveller,
  TravellerBoard,
  TravellerResult,
  TravellerSource,
)

# The assignment the page's own data is bound to, and so where reading starts.
# Its spacing carries no meaning — `var data = {...}` and `var data={...}` are
# one page to a browser — so the pattern tolerates any, rather than resting a
# whole capture on the captures' own habit. What follows is a JSON object, read
# with a decoder that stops at its closing brace rather than by matching braces
# here; the trailing `\s*` is what leaves the decoder pointed at the brace.
_BLOB_ASSIGNMENT_PATTERN = re.compile(r'var\s+data\s*=\s*')

# A played contract as the blob writes it — `4 S`, `3 NT x`: the level and
# strain separated by a space, and a doubling appended as a further space and
# one `x` per doubling. Two `x` at most, which is what
# `notation.PENALTY_BY_MARK_COUNT` has names for — a cell spelling more matches
# nothing and its row keeps its score without a contract.
_CONTRACT_PATTERN = re.compile(
  r"""
  (?P<level>[1-7])
  \s*(?P<strain>NT|[NSHDC])  # notrump as `NT` or `N`, a suit as its letter
  (?:\s*(?P<penalty>x{1,2}))?  # one `x` doubled, two redoubled
  """,
  re.VERBOSE | re.IGNORECASE,
)

# What the contract field holds for a board that was passed out.
_PASSOUT = 'PASS'

# The blob's own date format, e.g. `06/29/2026`.
_DATE_FORMAT = '%m/%d/%Y'

# How a pair summary names the direction a pair sat. A two-winner movement
# numbers its two directions separately, so the direction is what tells pair 5
# North-South from pair 5 East-West; a one-winner movement ranks its pairs as a
# single list and leaves the field null. The captures write `NS` and `EW`, and
# the hyphenated spellings are accepted alongside because the blob writes the
# same two sides as `N-S` and `E-W` in its vulnerability field.
_SUMMARY_SIDES: Mapping[str, Side] = {
  'N-S': Side.NORTH_SOUTH,
  'NS': Side.NORTH_SOUTH,
  'E-W': Side.EAST_WEST,
  'EW': Side.EAST_WEST,
}


# A hand record names one field per seat and suit — `north_spades` — so a field
# name is a seat prefix and a suit suffix joined. The suits run highest first.
_SUIT_FIELD_SUFFIXES = ('spades', 'hearts', 'diamonds', 'clubs')

# Every seat is spelled out in full here, unlike the compass letters the rest of
# the blob writes a seat as.
_SEAT_FIELD_PREFIXES: Mapping[Direction, str] = {
  Direction.NORTH: 'north',
  Direction.EAST: 'east',
  Direction.SOUTH: 'south',
  Direction.WEST: 'west',
}


# Every kind of thing this parser can fail to read, ranked by the shared ladder
# in travellers.md `#issue-reporting`.
_NO_PAGE_DATA = issue_reporting.Failure(
  'no_page_data', IssueSeverity.HIGH, 'boards'
)
_NO_SESSION = issue_reporting.Failure(
  'no_session', IssueSeverity.HIGH, 'boards'
)
_NO_PER_BOARD_RESULTS = issue_reporting.Failure(
  'no_per_board_results', IssueSeverity.HIGH, 'boards'
)
_UNREADABLE_BOARD_NUMBER = issue_reporting.Failure(
  'unreadable_board_number', IssueSeverity.HIGH, 'boards'
)
_EXTRA_SESSIONS = issue_reporting.Failure(
  'extra_sessions', IssueSeverity.MEDIUM, 'boards'
)
_UNREADABLE_DEAL = issue_reporting.Failure(
  'unreadable_deal', IssueSeverity.MEDIUM, 'deal'
)
_UNREADABLE_DOUBLE_DUMMY = issue_reporting.Failure(
  'unreadable_double_dummy', IssueSeverity.LOW, 'double_dummy_tricks'
)
_UNREADABLE_PAR = issue_reporting.Failure(
  'unreadable_par', IssueSeverity.LOW, 'par'
)


def parse_acbl_club_html(text: str, *, reference: str) -> Traveller:
  """Return the traveller an ACBL club-game page describes.

  Nothing is refused. A page carrying no readable data, and one describing an
  event that publishes no per-board results at all — a team game, whose page
  gives match scores instead — both come back as a traveller carrying an issue.
  A capture that yielded nothing is itself worth recording.

  Args:
    text: the page's whole contents, fetched or browser-saved.
    reference: how the capture is identified afterwards — the path it was saved
      to, or the URL it came from. Recorded on the traveller.
  """
  blob = _blob(text)
  data = blob.value
  issues = list(blob.issues)

  sessions = _list(data.get('sessions'))
  if data and not sessions:
    issues.append(_NO_SESSION.issue('the page describes no session'))
  if len(sessions) > 1:
    # A traveller covers one session, and every club game seen publishes one, so
    # a second means the page is a shape this parser has not been shown.
    issues.append(
      _EXTRA_SESSIONS.issue(
        f'the page describes {len(sessions)} sessions — only the first is read'
      )
    )
  session = _mapping(sessions[0]) if sessions else {}

  sections = [_mapping(section) for section in _list(session.get('sections'))]
  # Guarded on a session having been listed rather than on it holding anything,
  # so that a session stating nothing at all still reports the missing rows.
  if sessions and not sections:
    issues.append(
      _NO_PER_BOARD_RESULTS.issue(
        f'this {_text(data.get("type")) or "event"} publishes no per-board '
        f'results — only a pairs game carries a traveller'
      )
    )

  analysis = _analysis(session)
  return Traveller(
    source=TravellerSource.ACBL_CLUB,
    reference=reference,
    event=_text(data.get('name')),
    date=_date(_text(data.get('start_date'))),
    boards=_boards(sections, analysis=analysis.value),
    issues=(*issues, *analysis.issues),
  )


def _blob(text: str) -> issue_reporting.Read[Mapping[str, object]]:
  """The page's data blob, decoded, or nothing and the reason for nothing.

  Everything this parser reads comes out of the blob, so a page without a
  readable blob yields a traveller holding only the issue that says why.
  """
  assignment = _BLOB_ASSIGNMENT_PATTERN.search(text)
  if not assignment:
    return _no_page_data('no `var data` assignment in the page')
  try:
    decoded, _ = json.JSONDecoder().raw_decode(text, assignment.end())
  except json.JSONDecodeError:
    return _no_page_data('the page data is not readable JSON')
  if not isinstance(decoded, dict):
    return _no_page_data(
      f'the page data is a {type(decoded).__name__}, not an object'
    )
  return issue_reporting.Read(decoded)


def _no_page_data(message: str) -> issue_reporting.Read[Mapping[str, object]]:
  """No page data, and the reason there is none."""
  return issue_reporting.Read({}, issues=(_NO_PAGE_DATA.issue(message),))


@dataclasses.dataclass(frozen=True)
class _BoardAnalysis:
  """What a hand record says about a board, before any rows are read.

  The hand records are session-level — every section plays the same boards — so
  each record is read into a `_BoardAnalysis` once and looked up by board number
  as the sections' rows arrive. Holding the analysis in a type of its own,
  rather than in a `TravellerBoard` that has no rows yet, is what lets a board
  be built once and complete — its analysis and its rows together.
  """

  deal: Deal | None
  double_dummy_tricks: DoubleDummyTricks | None
  par: Par | None
  issues: tuple[Issue, ...]


def _analysis(
  session: Mapping[str, object],
) -> issue_reporting.Read[Mapping[int, _BoardAnalysis]]:
  """Read a session's hand records, one per board number.

  A session whose hand records were never uploaded yields no deals and no par,
  matching what the page says; the traveller's rows stand without them.

  Each part of a record is read on its own, so an unreadable double-dummy or par
  line costs that line alone and leaves the deal and the rows beside it intact.
  """
  by_board: dict[int, _BoardAnalysis] = {}
  issues: list[Issue] = []
  for record in _list(session.get('hand_records')):
    hand_record = _mapping(record)
    number = _integer(hand_record.get('board'))
    # A record's board number is what places it against the rows, so a record
    # without one has nowhere to go.
    if number is None:
      issues.append(
        _UNREADABLE_BOARD_NUMBER.issue(
          'dropped a hand record stating no board number'
        )
      )
      continue

    board_issues: list[Issue] = []
    double_dummy_tricks: DoubleDummyTricks | None = None
    par: Par | None = None
    try:
      double_dummy_tricks = acbl_notation.double_dummy_tricks(
        north_south=_text(hand_record.get('double_dummy_ns')),
        east_west=_text(hand_record.get('double_dummy_ew')),
      )
    except acbl_notation.AcblNotationError as error:
      board_issues.append(_UNREADABLE_DOUBLE_DUMMY.issue(str(error)))
    try:
      par = acbl_notation.par(
        _text(hand_record.get('par')), double_dummy_tricks=double_dummy_tricks
      )
    except acbl_notation.AcblNotationError as error:
      board_issues.append(_UNREADABLE_PAR.issue(str(error)))

    deal = _deal(hand_record)
    by_board[number] = _BoardAnalysis(
      deal=deal.value,
      double_dummy_tricks=double_dummy_tricks,
      par=par,
      issues=(
        *board_issues,
        *deal.issues,
        *notation.board_schedule_issues(
          board_number=number,
          dealer=_direction(_text(hand_record.get('dealer'))),
          vulnerability=_text(hand_record.get('vulnerability')) or None,
        ),
      ),
    )
  return issue_reporting.Read(by_board, issues=tuple(issues))


def _deal(
  hand_record: Mapping[str, object],
) -> issue_reporting.Read[Deal | None]:
  """The deal a hand record states, as one field per seat and suit.

  A record naming no seat at all states no deal, and a null deal says exactly
  that — so nothing is reported. A record naming some seats but not all is
  reported: the deal is dropped either way, but a null deal alone would not say
  that cards were there to lose.
  """
  hands: dict[Direction, Hand] = {}
  for seat, prefix in _SEAT_FIELD_PREFIXES.items():
    holdings = tuple(
      _text(hand_record.get(f'{prefix}_{suit}'))
      for suit in _SUIT_FIELD_SUFFIXES
    )
    if not any(holdings):
      if not hands:
        return issue_reporting.Read(None)
      return issue_reporting.Read(
        None,
        issues=(
          _UNREADABLE_DEAL.issue(
            f'the record states no cards for {seat} — its deal is dropped'
          ),
        ),
      )
    try:
      hands[seat] = notation.hand_from_holdings(holdings)
    except notation.NotationError as error:
      # An unreadable rank in one seat's holdings costs the whole deal: a
      # partial one would report cards nobody held.
      return issue_reporting.Read(
        None, issues=(_UNREADABLE_DEAL.issue(str(error)),)
      )

  try:
    return issue_reporting.Read(notation.deal_from_hands(hands))
  except notation.NotationError as error:
    return issue_reporting.Read(
      None, issues=(_UNREADABLE_DEAL.issue(str(error)),)
    )


def _boards(
  sections: Sequence[Mapping[str, object]],
  *,
  analysis: Mapping[int, _BoardAnalysis],
) -> tuple[TravellerBoard, ...]:
  """Every board of the session, each with every section's rows for it.

  Two sections playing board 3 make one board here, not two: the deal and par
  are the session's, so a board per section would carry the same analysis twice.
  Both sections' rows go onto the single board 3 instead.
  """
  results: dict[int, list[TravellerResult]] = {}
  for section in sections:
    name = _text(section.get('name')) or None
    players = _Players.read(section)
    for entry in _list(section.get('boards')):
      board = _mapping(entry)
      number = _integer(board.get('board_number'))
      if number is None:
        continue
      results.setdefault(number, []).extend(
        _result(_mapping(row), section=name, players=players)
        for row in _list(board.get('board_results'))
      )

  # A board the hand records cover but nobody played still belongs in the
  # record, and so does one played but absent from the hand records.
  unanalyzed = _BoardAnalysis(
    deal=None, double_dummy_tricks=None, par=None, issues=()
  )
  boards: list[TravellerBoard] = []
  for number in sorted(set(results) | set(analysis)):
    board_analysis = analysis.get(number, unanalyzed)
    boards.append(
      TravellerBoard(
        number=number,
        deal=board_analysis.deal,
        double_dummy_tricks=board_analysis.double_dummy_tricks,
        par=board_analysis.par,
        results=tuple(results.get(number, ())),
        issues=board_analysis.issues,
      )
    )
  return tuple(boards)


@dataclasses.dataclass(frozen=True)
class _PairKey:
  """What it takes to name one pair: its side and its number.

  The side is None where a summary states none — the mark of a movement that
  numbers every pair once, where the number identifies the pair on its own.
  """

  side: Side | None
  number: str


class _Players:
  """A section's pair summaries: who sat as each pair.

  A board row names its pairs by number alone, so the names come from here. The
  number is enough on its own in a movement that numbers every pair once; where
  a movement numbers the two directions separately, the summaries say which
  direction each number belongs to and the lookup uses both.
  """

  def __init__(self, by_pair: Mapping[_PairKey, tuple[str, ...]]) -> None:
    self._by_pair = by_pair

  @classmethod
  def read(cls, section: Mapping[str, object]) -> '_Players':
    """Read a section's pair summaries into a name lookup."""
    by_pair: dict[_PairKey, tuple[str, ...]] = {}
    for entry in _list(section.get('pair_summaries')):
      summary = _mapping(entry)
      number = _text(summary.get('pair_number'))
      if not number:
        continue
      side = _SUMMARY_SIDES.get(_text(summary.get('direction')))
      by_pair[_PairKey(side=side, number=number)] = tuple(
        acbl_notation.player_name(_text(_mapping(player).get('name')))
        for player in _list(summary.get('players'))
      )
    return cls(by_pair)

  def names(self, *, side: Side, number: str) -> tuple[str, ...]:
    """The pair's players, or nothing when no summary names them."""
    return self._by_pair.get(
      _PairKey(side=side, number=number)
    ) or self._by_pair.get(_PairKey(side=None, number=number), ())


def _result(
  row: Mapping[str, object], *, section: str | None, players: _Players
) -> TravellerResult:
  """One board row: who sat, what they played, and how it scored."""
  return TravellerResult(
    north_south=_pair(
      row, side=Side.NORTH_SOUTH, section=section, players=players
    ),
    east_west=_pair(row, side=Side.EAST_WEST, section=section, players=players),
    resolution=_resolution(row),
    score=_score(row),
    north_south_matchpoints=_number(row.get('ns_match_points')),
    east_west_matchpoints=_number(row.get('ew_match_points')),
  )


def _pair(
  row: Mapping[str, object],
  *,
  side: Side,
  section: str | None,
  players: _Players,
) -> PairIdentity:
  """One side of a board row, named from the section's pair summaries."""
  number = _text(row.get('ns_pair' if side == Side.NORTH_SOUTH else 'ew_pair'))
  return PairIdentity(
    number=number,
    side=side,
    section=section,
    names=players.names(side=side, number=number),
  )


def _resolution(row: Mapping[str, object]) -> Resolution | None:
  """What a row's contract resolved to, or None when it records none.

  The blob carries the trick count outright, so nothing has to be derived from
  the result token beside it.
  """
  contract = _text(row.get('contract')).strip()
  if contract.upper() == _PASSOUT:
    return Passout()

  match = _CONTRACT_PATTERN.fullmatch(contract)
  declarer = _direction(_text(row.get('declarer')))
  tricks_taken = _integer(row.get('tricks_taken'))
  if not match or not declarer or tricks_taken is None:
    return None

  return PlayedContract(
    contract=Contract(
      level=int(match.group('level')),
      strain=notation.STRAIN_BY_LETTER[match.group('strain').upper()],
      declarer=declarer,
      penalty=notation.PENALTY_BY_MARK_COUNT[len(match.group('penalty') or '')],
    ),
    result=Result(tricks_taken=tricks_taken),
  )


def _score(row: Mapping[str, object]) -> int | None:
  """A row's score, from North-South's perspective.

  The blob writes both sides' scores as the negation of each other, so either
  column alone gives the signed number; the East-West one stands in when the
  North-South one is missing.
  """
  if _text(row.get('contract')).strip().upper() == _PASSOUT:
    return 0
  north_south = _integer(row.get('ns_score'))
  if north_south is not None:
    return north_south
  east_west = _integer(row.get('ew_score'))
  return -east_west if east_west is not None else None


def _direction(value: str) -> Direction | None:
  """The seat a compass letter names, or None when it names none."""
  try:
    return Direction(value.strip().upper())
  except ValueError:
    return None


def _date(value: str) -> datetime.date | None:
  """The date the blob's own format states, or None when it states none."""
  try:
    return datetime.datetime.strptime(value.strip(), _DATE_FORMAT).date()
  except ValueError:
    return None


def _text(value: object) -> str:
  """A blob field as text, treating a field it left null as empty."""
  return value if isinstance(value, str) else ''


def _integer(value: object) -> int | None:
  """A blob field as a whole number; several are written as text."""
  if isinstance(value, bool):
    return None
  if isinstance(value, int):
    return value
  try:
    return int(_text(value).strip())
  except ValueError:
    return None


def _number(value: object) -> float | None:
  """A blob field as a number; the matchpoint fields are written as text."""
  if isinstance(value, bool):
    return None
  if isinstance(value, (int, float)):
    return float(value)
  try:
    return float(_text(value).strip())
  except ValueError:
    return None


def _mapping(value: object) -> Mapping[str, object]:
  """A blob value as an object, treating anything else as an empty one."""
  return value if isinstance(value, dict) else {}


def _list(value: object) -> Sequence[object]:
  """A blob value as an array, treating anything else as an empty one."""
  return value if isinstance(value, list) else ()
