# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read a Palo Alto club game's PBN into a traveller.

The club publishes each game through BridgeComposer, which writes a PBN file
alongside the HTML. PBN is a tagged, documented format, so it is much the easier
of the two to read: the deal, the double-dummy table, and par are tags, and the
traveller itself is a `ScoreTable` section.

What a PBN does not always carry is the traveller. Several of the club's
directors upload a hand record only — deals, double dummy, and par, with no
`ScoreTable` at all — so such a file yields a traveller whose boards have no
results. An empty traveller is a complete parse of what the file says, not a
failure; the HTML capture of the same game supplies the rows (see travellers.md
`#club-format`).

The comments below distinguish two kinds of claim, because the two age
differently. What the **PBN standard** fixes (version 2.1, `tistis.nl/pbn`)
holds for any program's files. What **BridgeComposer** does is observed in the
club's captures alone, and the club could switch programs: the `%HRTitle`
comment lines and the `ParContract` tag are extensions no standard defines, as
is every claim below about how a value is spaced or padded.

Names come out thinner here than from the HTML. A PBN row names a pair by its
players' surnames joined with a hyphen (`Alfa-Bravo`) and the file carries no
standings recap to look full names up in, so that hyphen is all there is to
split on — and a player whose own surname is hyphenated splits into two.
"""

import dataclasses
import datetime
import re
from collections.abc import Mapping, Sequence

from session_analysis import issue_reporting, notation
from session_analysis.enums import Direction, IssueSeverity, Side, Strain
from session_analysis.models import (
  CaptureReference,
  Deal,
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

# A tag pair, which is the whole of PBN's syntax that matters here:
# `[Board "7"]`, `[Vulnerable "N-S"]`, `[Event ""]`. Standard. Any line after a
# tag that does not open a tag of its own is that tag's table data.
_TAG_PATTERN = re.compile(
  r"""
  \[ (?P<name>\w+)          # the tag's name
  \s+ " (?P<value>[^"]*) "  # its value, always quoted and possibly empty
  \] \s* $
  """,
  re.VERBOSE,
)

# The title BridgeComposer prints above a hand record. It keeps that title in
# comment lines of its own: `%HRTitleEvent "Placeholder Pairs"`, `%HRTitleDate
# 2026.03.09`. Not standard, but the dependable source for the event and the
# date: every capture writes these, where the standard `[Event]` and `[Date]`
# tags are left empty often enough that neither can be relied on.
_TITLE_COMMENT_PATTERN = re.compile(
  r"""
  ^ %HRTitle (?P<field>Event|Date|Site)
  \s+ "? (?P<value>[^"]*) "?  # quoted or not: the date carries no quotes
  \s* $
  """,
  re.VERBOSE,
)

# One column of a table section's header. The standard gives a column its name,
# then optionally a backslash, the minimum width it is printed at, and a letter
# for how it is aligned within that width: `MP_NS\4R` is four wide and
# right-aligned, where `Declarer` states no width at all.
_COLUMN_PATTERN = re.compile(
  r"""
  (?P<name>\w+)
  (?: \\ (?P<width>\d+)
      (?P<alignment>\w)?     # matched only so the width ends where it should
  )?
  """,
  re.VERBOSE,
)

# A required space, not an optional one: a PBN's par tag always writes it, so
# demanding it keeps a run-together `NS4H+1` an issue rather than a silent read.
_SEAM = r'\s+'

# One contract of a par statement: `NS 4H+1`, `EW 6DX-5`, `N 2S=`. The whole
# `ParContract` tag is BridgeComposer's own, so every part of this shape is
# observed rather than standard.
_PAR_CONTRACT_PATTERN = re.compile(
  notation.DECLARER_PATTERN
  + _SEAM
  + notation.CONTRACT_PATTERN
  + notation.RESULT_PATTERN
)

# A par score: `NS 450`, `EW -1100`. The side named owns the score, so an
# East-West par states a positive number for a North-South loss. Standard tag
# (`OptimumScore`), observed shape.
_PAR_SCORE_PATTERN = re.compile(
  r"""
  (?P<side>NS|EW)
  \s+ (?P<score>[+-]?\d+)
  """,
  re.VERBOSE,
)


# What a score table writes in a cell it has no value for, e.g. the `Score_EW`
# of a row North-South scored. Observed.
_ABSENT = '-'

# What a tag writes to take its value from the nearest earlier record that
# stated one — every board record after the first writes `[Event "#"]`.
# Standard.
_REPEATS_PREVIOUS = '#'

# What a score table writes in the contract column of a board that was passed
# out. It appears in the score column too, in place of the zero both sides
# scored. Observed.
_PASSOUT = 'PASS'

# The standard's date format, always exactly ten characters. The fixed width is
# what allows a date to be partly unknown: a file that knows only the year must
# still fill the month and day positions, and the standard reserves `??` for
# digits the file cannot supply. So `2026.??.??` is a well-formed value and
# still not a date. No captured file has used `??` yet.
_DATE_FORMAT = '%Y.%m.%d'


class _ClubPbnFormatError(ValueError):
  """A table row did not fit the header its own section declared.

  Splitting a row is the one step that reports a failure by raising, because it
  runs below the level that knows what a failure there costs: the same split
  serves the score table and the double-dummy table, and those two record a bad
  row differently. Both callers catch it, so nothing raised here leaves the
  module.

  A tag the file simply omits is not this, and yields a traveller with the
  corresponding field empty and no issue at all.
  """


# Every kind of thing this parser can fail to read, ranked by the shared ladder
# in travellers.md `#issue-reporting`.
_NO_BOARD_RECORDS = issue_reporting.Failure(
  'no_board_records', IssueSeverity.HIGH, 'boards'
)
_UNREADABLE_BOARD_NUMBER = issue_reporting.Failure(
  'unreadable_board_number', IssueSeverity.HIGH, 'boards'
)
_UNREADABLE_ROW = issue_reporting.Failure(
  'unreadable_row', IssueSeverity.MEDIUM, 'results'
)
_UNREADABLE_CONTRACT = issue_reporting.Failure(
  'unreadable_contract', IssueSeverity.MEDIUM, 'resolution'
)
_UNREADABLE_DEAL = issue_reporting.Failure(
  'unreadable_deal', IssueSeverity.MEDIUM, 'deal'
)
_UNREADABLE_DEALER = issue_reporting.Failure(
  'unreadable_dealer', IssueSeverity.MEDIUM, 'dealer'
)
_UNREADABLE_DOUBLE_DUMMY_ROW = issue_reporting.Failure(
  'unreadable_double_dummy_row', IssueSeverity.LOW, 'double_dummy_tricks'
)
_UNREADABLE_PAR_SCORE = issue_reporting.Failure(
  'unreadable_par_score', IssueSeverity.LOW, 'par'
)
_UNREADABLE_PAR_CONTRACT = issue_reporting.Failure(
  'unreadable_par_contract', IssueSeverity.LOW, 'par'
)


@dataclasses.dataclass(frozen=True)
class _Table:
  """A PBN table section: the columns its tag declared, and its data rows.

  A table's tag value names the columns and the lines below it hold the data:

  ```
  [OptimumResultTable "Declarer;Denomination\\2R;Result\\2R"]
  N NT  9
  N  S 10
  ```
  """

  columns: tuple[str, ...]
  # The width each column was declared with, for the columns that declared one.
  widths: Mapping[str, int]
  rows: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _Record:
  """One PBN game — the standard's word for a file's unit of record.

  A game is a run of tag pairs and table data ending at a blank line. The word
  is inherited from chess notation and does not mean a session: in these files a
  game is one board, except for a leading game that carries the event tags and
  no board of its own.
  """

  tags: Mapping[str, str]
  tables: Mapping[str, _Table]


def parse_club_pbn(text: str, reference: CaptureReference) -> Traveller:
  """Return the traveller a club PBN file describes.

  Nothing is refused. A file holding no game, or a record this parser cannot
  place, comes back as a traveller carrying an issue rather than as a raised
  error — a capture that yielded nothing is itself worth recording.

  Args:
    text: the file's whole contents.
    reference: how the capture is identified afterwards, so a stored record
      traces back to the file it was parsed from. Recorded on the traveller
      unchanged.
  """
  title = _title_comments(text)
  records = _read_records(text)
  # A file may open with a game carrying only the shared event tags and no board
  # of its own; the boards are the games that name one.
  board_records = tuple(record for record in records if 'Board' in record.tags)

  issues: list[Issue] = []
  if not board_records:
    issues.append(_NO_BOARD_RECORDS.issue('the file holds no board records'))

  boards: list[TravellerBoard] = []
  for record in board_records:
    number = record.tags['Board'].strip()
    # A board's number is what the deal, the schedule, and the join to the sheet
    # all hang off, so a record with no readable number has nowhere to go.
    # Recording the number as written is what keeps the record from vanishing.
    if not number.isdigit():
      issues.append(
        _UNREADABLE_BOARD_NUMBER.issue(
          f'dropped a board record numbered {number!r}'
        )
      )
      continue
    boards.append(_board_from_record(record, number=int(number)))

  return Traveller(
    source=TravellerSource.CLUB_PBN,
    reference=reference,
    event=title.get('Event') or _first_tag(records, 'Event'),
    date=_date(title.get('Date') or _first_tag(records, 'Date')),
    boards=tuple(boards),
    issues=tuple(issues),
  )


def _first_tag(records: Sequence[_Record], name: str) -> str:
  """The first value any game states for a tag, or empty if none states one.

  A tag whose value is the same all through a file is written out once and then
  repeated with `#`, which the standard defines as "take the value from the
  nearest earlier game". The club's directors also leave several such tags empty
  outright, so the opening game is not reliably the one that states the value:

  ```
  [Event ""]        <- the opening game, saying nothing
  [Event "Monday Pairs"]
  [Event "#"]       <- and every board after it, repeating
  ```

  Walking forward for the first game that states something resolves both.
  """
  for record in records:
    value = record.tags.get(name, '').strip()
    if value and value != _REPEATS_PREVIOUS:
      return value
  return ''


def _title_comments(text: str) -> Mapping[str, str]:
  """The event, date, and site from BridgeComposer's hand-record title lines."""
  found: dict[str, str] = {}
  for line in text.splitlines():
    if not line.startswith('%'):
      # The title comments sit in the file's header block, so the first line
      # that is not a comment is past them and ends the search.
      if line.strip():
        break
      continue
    match = _TITLE_COMMENT_PATTERN.match(line)
    if match:
      found[match.group('field')] = match.group('value').strip()
  return found


def _date(value: str) -> datetime.date | None:
  """The date a PBN date field states, or None when it states none.

  Two ordinary cases yield no date, and neither is worth an issue: the club's
  directors often leave the field empty, and `??` is how the standard spells a
  part of the date the file does not know (see `_DATE_FORMAT`). In both the file
  is declining to state a date rather than stating one badly — the distinction
  `TravellerResult.issues` draws.
  """
  try:
    return datetime.datetime.strptime(value.strip(), _DATE_FORMAT).date()
  except ValueError:
    return None


def _read_records(text: str) -> Sequence[_Record]:
  """Split a PBN file into its games, which in these files means its boards.

  A game runs until a blank line. Within it, a tag line opens a tag, and every
  following line that does not open a tag of its own is table data belonging to
  the tag that did.
  """
  records: list[_Record] = []
  tags: dict[str, str] = {}
  tables: dict[str, _Table] = {}
  open_table: str | None = None
  rows: list[str] = []

  def close_table() -> None:
    """Attach the rows collected so far to the table tag that opened them."""
    nonlocal open_table
    if open_table:
      header = tables[open_table]
      tables[open_table] = dataclasses.replace(header, rows=tuple(rows))
    open_table = None
    rows.clear()

  def close_record() -> None:
    """Finish the game being read, if it holds anything."""
    close_table()
    if tags:
      records.append(_Record(tags=dict(tags), tables=dict(tables)))
    tags.clear()
    tables.clear()

  for line in text.splitlines():
    if line.startswith('%'):
      # A comment. The header's title comments are read separately; every other
      # comment is BridgeComposer's own rendering options.
      continue
    if not line.strip():
      # The standard ends a game at a line holding nothing but whitespace.
      close_record()
      continue

    match = _TAG_PATTERN.match(line.strip())
    if match:
      close_table()
      name, value = match.group('name'), match.group('value')
      tags[name] = value
      if name.endswith('Table'):
        tables[name] = _parse_table_header(value)
        open_table = name
      continue

    if open_table:
      rows.append(line)

  close_record()
  return tuple(records)


def _parse_table_header(value: str) -> _Table:
  """Read a table tag's value into the columns it declares.

  A header names its columns in order, separated by semicolons, each optionally
  carrying the minimum width it is printed at — `Names_NS\\17`. The widths
  matter for exactly one column: the one holding names, whose value is the only
  one that may contain a space and so cannot be found by splitting on
  whitespace.
  """
  columns: list[str] = []
  widths: dict[str, int] = {}
  for column in value.split(';'):
    match = _COLUMN_PATTERN.match(column.strip())
    if not match:
      continue
    columns.append(match.group('name'))
    if match.group('width'):
      widths[match.group('name')] = int(match.group('width'))
  return _Table(columns=tuple(columns), widths=widths, rows=())


def _read_row(table: _Table, row: str) -> Mapping[str, str]:
  """Split one data row into its columns.

  Every value but a name is a single token, so the row splits on whitespace up
  to the first name column. From there the declared widths take over, because a
  name may contain a space and the two name columns sit at the end:

  ```
  [ScoreTable "PairId_NS\\2R;Contract\\4L;Names_NS\\13;Names_EW"]
   1 4S   Alfa-Bravo    Charlie-Delta
  ```

  Raises:
    _ClubPbnFormatError: if the row has fewer values than the header declared.
  """
  name_columns = [
    column for column in table.columns if column.startswith('Names')
  ]
  if not name_columns:
    values = row.split()
    if len(values) != len(table.columns):
      raise _ClubPbnFormatError(
        f'table row has {len(values)} values for {len(table.columns)} '
        f'columns: {row!r}'
      )
    return dict(zip(table.columns, values, strict=True))

  leading = table.columns.index(name_columns[0])
  parts = row.split(maxsplit=leading)
  if len(parts) <= leading:
    raise _ClubPbnFormatError(
      f'table row has {len(parts)} values before its name columns, expected '
      f'{leading + 1}: {row!r}'
    )

  read = dict(zip(table.columns[:leading], parts[:leading], strict=True))
  remainder = parts[leading]
  for column in name_columns[:-1]:
    end = _name_column_end(remainder, table.widths.get(column, len(remainder)))
    read[column] = remainder[:end].strip()
    remainder = remainder[end:].lstrip()
  read[name_columns[-1]] = remainder.strip()
  return read


def _name_column_end(remainder: str, width: int) -> int:
  """Where a name column ends within the rest of its row.

  The standard makes a declared width a *minimum*, not the width the column was
  printed at: a value short enough is padded out to the declared width, and a
  value too long simply runs past that width, pushing every column to its right
  along. So the column ends at the declared width when the character sitting
  there is the space that separates two columns, and at the next space when the
  value overran instead. Running on to the next space is what keeps a long pair
  of surnames whole.
  """
  end = width
  while end < len(remainder) and not remainder[end].isspace():
    end += 1
  return end


def _board_from_record(record: _Record, *, number: int) -> TravellerBoard:
  """Read one board record — its deal, its analysis, and its traveller rows.

  Each part is read on its own and reports its own failures, so an unreadable
  deal costs the deal alone and leaves the rows the board was played at intact.
  """
  issues: list[Issue] = []

  printed_dealer = record.tags.get('Dealer', '').strip()
  dealer = notation.parse_seat(printed_dealer)
  # An unreadable dealer costs only the cross-check below. The dealer follows
  # from the board number and is never stored, so nothing but that check wanted
  # this value — but staying silent would hide a tag gone strange.
  if printed_dealer and not dealer:
    issues.append(
      _UNREADABLE_DEALER.issue(f'unreadable dealer {printed_dealer!r}')
    )

  deal = _deal(record.tags.get('Deal', ''))
  double_dummy = _makeable_tricks(record.tables.get('OptimumResultTable'))
  par = _par(record, double_dummy_tricks=double_dummy.value)
  results = _results(record.tables.get('ScoreTable'))

  return TravellerBoard(
    number=number,
    deal=deal.value,
    double_dummy_tricks=double_dummy.value,
    par=par.value,
    results=results.value,
    issues=(
      *issues,
      *deal.issues,
      *double_dummy.issues,
      *par.issues,
      *results.issues,
      *notation.board_schedule_issues(
        board_number=number,
        dealer=dealer,
        vulnerability=record.tags.get('Vulnerable') or None,
      ),
    ),
  )


def _deal(value: str) -> issue_reporting.Read[Deal | None]:
  """The deal a `[Deal]` tag states, or None when the tag states none.

  The tag names the seat it starts at and then lists the four hands clockwise
  from there, each as its four suit holdings separated by dots: `[Deal
  "N:K62.AKT4.Q97.A76 Q53.J92.AKT3.KJ8 A97.65.J8542.QT9 JT84.Q873.6.J543"]`.

  A deal is four whole hands or it is nothing — a partial one would report cards
  nobody held — so anything unreadable within a deal costs the whole deal.
  """
  value = value.strip()
  if not value:
    return issue_reporting.Read(None)

  first_seat, _, hands_text = value.partition(':')
  start = notation.parse_seat(first_seat)
  if not start:
    return _unreadable_deal(f'deal names no starting seat: {value!r}')

  clockwise = notation.SEATS_CLOCKWISE
  hands_text_by_seat = hands_text.split()
  if len(hands_text_by_seat) != len(clockwise):
    return _unreadable_deal(
      f'deal has {len(hands_text_by_seat)} hands, expected {len(clockwise)}: '
      f'{value!r}'
    )

  offset = clockwise.index(start)
  try:
    hands = {
      clockwise[(offset + position) % len(clockwise)]: (
        notation.hand_from_holdings(hand.split('.'))
      )
      for position, hand in enumerate(hands_text_by_seat)
    }
    return issue_reporting.Read(notation.deal_from_hands(hands))
  except notation.NotationError as error:
    # An unreadable rank, or a suit holding the tag left out.
    return _unreadable_deal(str(error))


def _unreadable_deal(message: str) -> issue_reporting.Read[Deal | None]:
  """No deal, and the reason there is none."""
  return issue_reporting.Read(None, issues=(_UNREADABLE_DEAL.issue(message),))


def _makeable_tricks(
  table: _Table | None,
) -> issue_reporting.Read[DoubleDummyTricks | None]:
  """The double-dummy table an `[OptimumResultTable]` section states.

  This section is read rather than BridgeComposer's `[DoubleDummyTricks]` tag,
  whose twenty hex digits carry the same numbers positionally. The section names
  a declarer and a denomination on every row, so nothing rests on an assumed
  ordering — and naming each cell is also what lets one row be skipped, where a
  positional reading would have to guess how many digits an unreadable row stood
  for.
  """
  if not table:
    return issue_reporting.Read(None)

  tricks: dict[Direction, dict[Strain, int | None]] = {}
  issues: list[Issue] = []
  for row in table.rows:
    try:
      read = _read_row(table, row)
    except _ClubPbnFormatError as error:
      issues.append(_UNREADABLE_DOUBLE_DUMMY_ROW.issue(str(error)))
      continue

    declarer = notation.parse_seat(read.get('Declarer', ''))
    strain = notation.STRAIN_BY_LETTER.get(read.get('Denomination', '').upper())
    tricks_won = read.get('Result', '')
    if not declarer or not strain or not tricks_won.isdigit():
      issues.append(
        _UNREADABLE_DOUBLE_DUMMY_ROW.issue(
          f'unreadable double-dummy row: {row!r}'
        )
      )
      continue
    tricks.setdefault(declarer, {})[strain] = int(tricks_won)

  # A table with no readable rows at all is no table: None is what stands for no
  # analysis, where an empty mapping would claim an analysis that said nothing.
  return issue_reporting.Read(tricks or None, issues=tuple(issues))


def _par(
  record: _Record, *, double_dummy_tricks: DoubleDummyTricks | None
) -> issue_reporting.Read[Par | None]:
  """The par an `[OptimumScore]` and `[ParContract]` pair state.

  The score is the primary fact and the contracts are the ways to reach it, so
  an unreadable contract costs that contract while the score stands, and an
  unreadable score costs the whole par.
  """
  stated_score = record.tags.get('OptimumScore', '').strip()
  if not stated_score:
    return issue_reporting.Read(None)

  score_match = _PAR_SCORE_PATTERN.fullmatch(stated_score)
  if not score_match:
    return issue_reporting.Read(
      None,
      issues=(
        _UNREADABLE_PAR_SCORE.issue(f'unreadable par score: {stated_score!r}'),
      ),
    )
  score = int(score_match.group('score'))
  # The tag states the score from the named side's own perspective, so `EW 1100`
  # is East-West up 1100 and North-South down it. Every traveller field states a
  # score from North-South's side, so an East-West par flips sign.
  if Side(score_match.group('side')) == Side.EAST_WEST:
    score = -score

  resolutions: list[Resolution] = []
  issues: list[Issue] = []
  for statement in record.tags.get('ParContract', '').split(';'):
    statement = statement.strip()
    if not statement:
      continue
    match = _PAR_CONTRACT_PATTERN.fullmatch(statement)
    if not match:
      issues.append(
        _UNREADABLE_PAR_CONTRACT.issue(
          f'unreadable par contract: {statement!r}'
        )
      )
      continue

    level = int(match.group('level'))
    try:
      resolutions.extend(
        notation.par_contracts(
          level=level,
          strain=notation.STRAIN_BY_LETTER[match.group('strain')],
          penalty=notation.PENALTY_BY_MARK_COUNT[len(match.group('penalty'))],
          declarer=notation.declarer_from_token(match.group('declarer')),
          stated_tricks=notation.tricks_taken_from_par_result(
            match.group('result') or '', level
          ),
          double_dummy_tricks=double_dummy_tricks,
        )
      )
    except notation.NotationError as error:
      # An unreadable result, or one the statement omits with no double-dummy
      # table to recover it from.
      issues.append(_UNREADABLE_PAR_CONTRACT.issue(str(error)))

  return issue_reporting.Read(
    Par(score=score, resolutions=tuple(resolutions)), issues=tuple(issues)
  )


def _results(
  table: _Table | None,
) -> issue_reporting.Read[tuple[TravellerResult, ...]]:
  """The traveller rows a `[ScoreTable]` section holds.

  A file with no score table yields no rows. Several of the club's directors
  upload exactly that: a hand record of deals and analysis, carrying no table of
  results at all. An empty tuple is the honest reading of such a file, not a
  failure to find rows in it.
  """
  if not table:
    return issue_reporting.Read(())

  rows: list[TravellerResult] = []
  issues: list[Issue] = []
  for row in table.rows:
    if not row.strip():
      continue
    try:
      read = _read_row(table, row)
    except _ClubPbnFormatError as error:
      # A row that cannot be split names no pair, and a row naming no pair joins
      # to nothing later, so the row's text is kept in the issue instead.
      issues.append(_UNREADABLE_ROW.issue(str(error)))
      continue
    rows.append(_result(read))

  return issue_reporting.Read(tuple(rows), issues=tuple(issues))


def _result(read: Mapping[str, str]) -> TravellerResult:
  """One traveller row: who sat, what they played, and how it scored."""
  section = read.get('Section', '').strip()
  resolution = _resolution(read)
  return TravellerResult(
    north_south=_pair(read, side=Side.NORTH_SOUTH, section=section),
    east_west=_pair(read, side=Side.EAST_WEST, section=section),
    resolution=resolution.value,
    score=_score(read),
    north_south_matchpoints=_number(read.get('MP_NS', '')),
    east_west_matchpoints=_number(read.get('MP_EW', '')),
    issues=resolution.issues,
  )


def _pair(read: Mapping[str, str], *, side: Side, section: str) -> PairIdentity:
  """One side of a traveller row: its number, section, and players."""
  names = read.get(f'Names_{side}', '').strip()
  return PairIdentity(
    number=read.get(f'PairId_{side}', '').strip(),
    side=side,
    section=section if section and section != _ABSENT else None,
    # The row gives surnames joined by a hyphen and nothing to tell that hyphen
    # from one inside a surname; splitting on it is the best the file supports.
    names=tuple(name for name in names.split('-') if name),
  )


def _resolution(
  read: Mapping[str, str],
) -> issue_reporting.Read[Resolution | None]:
  """What a row's contract column resolved to, or None when it names none."""
  written = notation.normalize(read.get('Contract', ''))
  if written == _PASSOUT:
    return issue_reporting.Read(Passout())

  contract = notation.parse_contract(
    written, declarer=notation.parse_seat(read.get('Declarer', ''))
  )
  tricks_won = read.get('Result', '').strip()
  if not contract or not tricks_won.isdigit():
    # A row naming no contract at all is a legitimate state — a board never
    # played, or one the director adjusted — so only a row that named one and
    # then would not read is worth reporting.
    if not written or written == _ABSENT:
      return issue_reporting.Read(None)
    return issue_reporting.Read(
      None,
      issues=(
        _UNREADABLE_CONTRACT.issue(
          f'unreadable contract {written!r} by {read.get("Declarer")!r} with '
          f'result {tricks_won!r}'
        ),
      ),
    )

  return issue_reporting.Read(
    PlayedContract(
      contract=contract,
      # The standard defines this column as the tricks declarer won, so it is
      # already the canonical count and needs no translation.
      result=Result(tricks_taken=int(tricks_won)),
    )
  )


def _score(read: Mapping[str, str]) -> int | None:
  """A row's score, from North-South's perspective.

  The table prints a score in whichever side's column it is positive for and
  leaves the other blank, so the two columns collapse to one signed number. A
  passed-out board scores nothing for either side, and the table writes that
  empty score as `PASS` in the score column rather than as a zero.
  """
  if read.get('Contract', '').strip().upper() == _PASSOUT:
    return 0
  north_south = _number(read.get('Score_NS', ''))
  if north_south is not None:
    return int(north_south)
  east_west = _number(read.get('Score_EW', ''))
  if east_west is not None:
    return -int(east_west)
  return None


def _number(value: str) -> float | None:
  """A numeric cell's value, or None for the dash a table writes for absent."""
  try:
    return float(value.strip())
  except ValueError:
    return None
