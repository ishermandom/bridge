# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read an ACBL tournament session summary into a traveller.

A session summary at `live.acbl.org/event/...` carries no data blob. Its board
panels and its results tables arrive already built in the server's own response,
and the page's scripts only sort and page what is there — so the markup is the
whole of what a capture holds, and the whole of what there is to read.

A tournament has only this one traveller source: no club site publishes the same
game, so nothing cross-checks what this parser produces. Internal consistency
stands in for that — typically, every row's two sides' matchpoints reach the
same total, which is what a mis-joined row would break, and every published
score resolves to exactly one trick count. The first is strong evidence rather
than a law: for example, a director awarding an average-plus to both sides puts
that row off the total.

The page prints a score on every row but never a trick count. The cell that
would carry one is emitted inside an HTML comment, and is empty inside it, so
reading the comment would gain nothing. The count is recovered instead by
scoring the contract against the published score — see `scoring`.
"""

import dataclasses
import datetime
import re
from collections.abc import Iterator, Mapping, Sequence

import bs4

from session_analysis import (
  acbl_notation,
  board_rotation,
  issue_reporting,
  notation,
  scoring,
)
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Side,
  Strain,
)
from session_analysis.models import (
  Contract,
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

# The class on each empty span that stands for a suit, and the strain it names.
# The glyph itself is drawn by the stylesheet, so the class is the only place
# the suit is written down in the HTML markup.
_STRAIN_CLASSES: Mapping[str, Strain] = {
  'spades': Strain.SPADES,
  'hearts': Strain.HEARTS,
  'diams': Strain.DIAMONDS,
  'clubs': Strain.CLUBS,
}

# A board panel's id, which is where a board states its number in a form that
# does not depend on reading the rendered heading beside it.
_BOARD_ID_PATTERN = re.compile(r'^board-(?P<number>\d+)$')

# The dealer and vulnerability the panel prints above the diagram.
_DEALER_PATTERN = re.compile(r'Dlr:\s*(?P<dealer>[NESW])')
_VULNERABILITY_PATTERN = re.compile(r'Vul:\s*(?P<vulnerability>\S+)')

# The event's date and name, from the two headings the page opens with —
# `Jun 27, 2026 - Saturday 10:00 am` and `Open Pairs Event Summary`.
_HEADING_DATE_PATTERN = re.compile(
  r'(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})'
)
_HEADING_DATE_FORMAT = '%b %d %Y'
_EVENT_HEADING_SUFFIX = 'Event Summary'

# The section a heading introduces above the board panels belonging to it.
_SECTION_PATTERN = re.compile(r'Section\s+(?P<name>\S+)')

# A played contract in a results row: the level, the suit's now-substituted
# letter, and a lowercase `x` for each doubling. Two `x` at most, which is what
# `notation.PENALTY_BY_MARK_COUNT` has names for — a cell spelling more matches
# nothing and its row keeps its score without a contract. The cell reaches the
# pattern with its whitespace already taken out, so no piece here allows any.
_CONTRACT_PATTERN = re.compile(
  r"""
  (?P<level>[1-7])
  (?P<strain>NT|[NSHDC])  # notrump as `NT` or `N`, a suit as its letter
  (?P<penalty>x{0,2})  # one `x` doubled, two redoubled, none undoubled
  """,
  re.VERBOSE | re.IGNORECASE,
)

# What a results row writes in its score column for a board that was passed out.
# The contract column is blank, exactly as it is for a board nobody played, so
# this is the only thing that tells the two apart.
_PASSOUT = 'PASS'

# A pair's number where a results row introduces it. Matched against the cell's
# loose text runs one at a time, so the anchor means "at the end of this run" —
# what marks the digits as a pair number is the players' spans starting right
# after them, not their being the only digits in the cell.
_PAIR_NUMBER_PATTERN = re.compile(
  r"""
  (?P<number>\d+)-  # the `15-` of `15-Mike Alfa-Nora Bravo`
  \s*$  # nothing but space may follow, because the players' spans come next
  """,
  re.VERBOSE,
)

# The heading above each of a board's two results tables, naming the side the
# table's scores and matchpoints are stated from.
_TABLE_SIDES: Mapping[str, Side] = {
  'N-S': Side.NORTH_SOUTH,
  'E-W': Side.EAST_WEST,
}

# Where each value sits among a results row's cells. Two cells go unnamed
# because nothing here wants them: cell 0 holds a menu button, and cell 5 holds
# the percentage that the matchpoints in cell 4 already fix. The trick count is
# not a cell at all — the page emits that column inside an HTML comment, and
# empty at that, so it takes up no position.
_CONTRACT_COLUMN = 1
_DECLARER_COLUMN = 2
_SCORE_COLUMN = 3
_MATCHPOINTS_COLUMN = 4
_PAIRS_COLUMN = 6


# Every kind of thing this parser can fail to read, ranked by the shared ladder
# in travellers.md `#issue-reporting`.
_NO_BOARD_PANELS = issue_reporting.Failure(
  'no_board_panels', IssueSeverity.HIGH, 'boards'
)
_NO_RESULTS_TABLE = issue_reporting.Failure(
  'no_results_table', IssueSeverity.HIGH, 'results'
)
_UNREADABLE_DOUBLE_DUMMY = issue_reporting.Failure(
  'unreadable_double_dummy', IssueSeverity.LOW, 'double_dummy_tricks'
)
_UNREADABLE_PAR = issue_reporting.Failure(
  'unreadable_par', IssueSeverity.LOW, 'par'
)
_UNSCORABLE_RESULT = issue_reporting.Failure(
  'unscorable_result', IssueSeverity.MEDIUM, 'resolution'
)


@dataclasses.dataclass(frozen=True)
class _RowPair:
  """One of the two pairs a results row names: its number and its players.

  Deliberately carries no side. Nothing about a pair fixes which side it sat —
  in a one-winner movement a pair sits both ways over a session — so the side is
  settled per row by `_pairs` and attached by `_pair`.
  """

  number: str
  names: tuple[str, ...]


@dataclasses.dataclass
class _MutableRowPair:
  """A `_RowPair` part-way through being read out of a results row's cell.

  The number arrives first and each player's name follows in a span of its own,
  so the names accumulate after the pair is opened. Mutable for exactly that
  reason, and frozen into a `_RowPair` once the cell is exhausted.
  """

  number: str
  names: list[str] = dataclasses.field(default_factory=list)


def parse_acbl_tournament_html(text: str, *, reference: str) -> Traveller:
  """Return the traveller an ACBL tournament session summary describes.

  Nothing is refused. A page holding no board panels, and a panel this parser
  cannot place, both come back as a traveller carrying an issue rather than as a
  raised error — a capture that yielded nothing is itself worth recording.

  Args:
    text: the summary page's whole contents.
    reference: how the capture is identified afterwards — the path it was saved
      to, or the URL it came from. Recorded on the traveller.
  """
  soup = bs4.BeautifulSoup(text, 'html.parser')
  _replace_suit_glyphs(soup)

  boards = tuple(
    _board(found.panel, number=found.number, section=found.section)
    for found in _panels(soup)
  )
  return Traveller(
    source=TravellerSource.ACBL_TOURNAMENT,
    reference=reference,
    event=_event(soup),
    date=_date(soup),
    boards=boards,
    issues=()
    if boards
    else (_NO_BOARD_PANELS.issue('the page holds no board panels'),),
  )


def _replace_suit_glyphs(soup: bs4.BeautifulSoup) -> None:
  """Swap every suit span for the letter of the strain it names.

  The spans are empty — the suit is drawn from the class by the stylesheet — so
  replacing each with its letter is what makes the rest of the page plain text.
  """
  for glyph in soup.find_all('span', class_=list(_STRAIN_CLASSES)):
    strain = next(
      (
        _STRAIN_CLASSES[name]
        for name in (glyph.get('class') or [])
        if name in _STRAIN_CLASSES
      ),
      None,
    )
    if strain:
      glyph.replace_with(strain.value)


def _event(soup: bs4.BeautifulSoup) -> str:
  """The event's name, from the heading that announces the summary."""
  for heading in soup.find_all('h2'):
    text = _flattened(heading)
    if text.endswith(_EVENT_HEADING_SUFFIX):
      return text[: -len(_EVENT_HEADING_SUFFIX)].strip()
  return ''


def _date(soup: bs4.BeautifulSoup) -> datetime.date | None:
  """The session's date, from the heading the page opens with."""
  heading = soup.find('h1')
  match = _HEADING_DATE_PATTERN.search(_flattened(heading)) if heading else None
  if not match:
    return None
  spelled = f'{match.group("month")} {match.group("day")} {match.group("year")}'
  try:
    return datetime.datetime.strptime(spelled, _HEADING_DATE_FORMAT).date()
  except ValueError:
    return None


@dataclasses.dataclass(frozen=True)
class _SectionPanel:
  """One board panel: the board it holds and the section it sat under."""

  section: str | None
  panel: bs4.Tag
  number: int


def _panels(soup: bs4.BeautifulSoup) -> Iterator[_SectionPanel]:
  """Every board panel, with its number and the section heading above it.

  A `div` is a board panel exactly when its id states a board number, so the
  same read both recognizes a panel and gives the number it is yielded with.
  Sections are headings rather than containers, so a panel belongs to whichever
  one most recently preceded it.
  """
  section: str | None = None
  for element in soup.find_all(['div', 'h3']):
    if element.name == 'h3':
      if 'section' in (element.get('class') or []):
        match = _SECTION_PATTERN.search(_flattened(element))
        if match:
          section = match.group('name')
      continue
    number = _board_number(element)
    if number is not None:
      yield _SectionPanel(section=section, panel=element, number=number)


def _board_number(element: bs4.Tag) -> int | None:
  """The board number a panel's id states, or None if it states none."""
  match = _BOARD_ID_PATTERN.match(str(element.get('id') or ''))
  return int(match.group('number')) if match else None


def _flattened(element: bs4.Tag) -> str:
  """An element's text with every run of whitespace collapsed to one space."""
  return ' '.join(element.get_text(' ').split())


def _board(
  panel: bs4.Tag, *, number: int, section: str | None
) -> TravellerBoard:
  """Read one board — its deal, its double-dummy analysis, and its rows."""
  double_dummy = _makeable_tricks(panel)
  par = _par(panel, double_dummy_tricks=double_dummy.value)
  results = _results(panel, board_number=number, section=section)

  return TravellerBoard(
    number=number,
    deal=_deal(panel),
    double_dummy_tricks=double_dummy.value,
    par=par.value,
    results=results.value,
    issues=(
      *double_dummy.issues,
      *par.issues,
      *results.issues,
      *_schedule_issues(panel, board_number=number),
    ),
  )


def _par(
  panel: bs4.Tag, *, double_dummy_tricks: DoubleDummyTricks | None
) -> issue_reporting.Read[Par | None]:
  """The par the panel states, or None when it prints no par block."""
  par_score = panel.find('div', class_='par-score')
  if not par_score:
    return issue_reporting.Read(None)
  try:
    return issue_reporting.Read(
      acbl_notation.par(
        _value_span_text(par_score), double_dummy_tricks=double_dummy_tricks
      )
    )
  except acbl_notation.AcblNotationError as error:
    return issue_reporting.Read(
      None, issues=(_UNREADABLE_PAR.issue(str(error)),)
    )


def _schedule_issues(panel: bs4.Tag, *, board_number: int) -> Sequence[Issue]:
  """Report a printed dealer or vulnerability contradicting the board number."""
  printed = panel.find('div', class_='board-data')
  text = _flattened(printed) if printed else ''
  dealer = _DEALER_PATTERN.search(text)
  vulnerability = _VULNERABILITY_PATTERN.search(text)
  return notation.board_schedule_issues(
    board_number=board_number,
    dealer=Direction(dealer.group('dealer')) if dealer else None,
    vulnerability=(
      vulnerability.group('vulnerability') if vulnerability else None
    ),
  )


def _makeable_tricks(
  panel: bs4.Tag,
) -> issue_reporting.Read[DoubleDummyTricks | None]:
  """The double-dummy table the panel's two analysis lines state."""
  analysis = panel.find('div', class_='double-dummy')
  if not analysis:
    return issue_reporting.Read(None)
  lines = [
    _flattened(line) for line in analysis.find_all('span', recursive=False)
  ]
  # The block states one line per side. A block holding any other number of
  # lines means the markup has moved, and dropping it quietly would lose the
  # analysis without a word.
  if len(lines) != 2:
    return issue_reporting.Read(
      None,
      issues=(
        _UNREADABLE_DOUBLE_DUMMY.issue(
          f'the double-dummy block states {len(lines)} lines, not two'
        ),
      ),
    )
  try:
    return issue_reporting.Read(
      acbl_notation.double_dummy_tricks(
        north_south=lines[0], east_west=lines[1]
      )
    )
  except acbl_notation.AcblNotationError as error:
    return issue_reporting.Read(
      None, issues=(_UNREADABLE_DOUBLE_DUMMY.issue(str(error)),)
    )


def _value_span_text(element: bs4.Tag) -> str:
  """The text of the block's own value span.

  Both the double-dummy and par blocks open with a link explaining themselves
  and follow the link with the value, so the value is the block's first span.
  The span has to be the block's *own* child rather than the last span anywhere
  inside the block: the renderer wraps a doubling's asterisk in a span of its
  own, and line-wraps a long par into a nested div, either of which would
  otherwise be read as the value.
  """
  span = element.find('span', recursive=False)
  return _flattened(span) if span else ''


def _deal(panel: bs4.Tag) -> Deal | None:
  """The deal the panel's diagram states.

  The diagram lays the hands out as they sit at the table: the top and bottom
  blocks are North and South, and the middle block holds West on its left and
  East on its right.
  """
  outer = [
    hand
    for hand in panel.find_all('div', class_='hand')
    if 'middle' not in (hand.get('class') or [])
  ]
  middle = panel.find('div', class_='middle')
  if len(outer) != 2 or not middle:
    return None

  west = middle.find('div', class_='left')
  east = middle.find('div', class_='right')
  if not west or not east:
    return None

  return notation.deal_from_hands(
    {
      Direction.NORTH: notation.hand_from_holdings(_holdings(outer[0])),
      Direction.WEST: notation.hand_from_holdings(_holdings(west)),
      Direction.EAST: notation.hand_from_holdings(_holdings(east)),
      Direction.SOUTH: notation.hand_from_holdings(_holdings(outer[1])),
    }
  )


def _holdings(hand: bs4.Tag) -> Sequence[str]:
  """One hand's four suit holdings, highest suit first.

  Each holding is a span opening with the suit's now-substituted letter and
  continuing with the ranks held in it, so the suit is read off the front rather
  than assumed from the span's position.
  """
  by_suit: dict[str, str] = {}
  for holding in hand.find_all('span', recursive=False):
    suit, _, ranks = _flattened(holding).partition(' ')
    by_suit[suit.upper()] = ranks
  return tuple(
    by_suit.get(suit.value, '') for suit in notation.SUITS_HIGH_TO_LOW
  )


def _results(
  panel: bs4.Tag, *, board_number: int, section: str | None
) -> issue_reporting.Read[tuple[TravellerResult, ...]]:
  """The traveller rows the board's two results tables hold.

  The page prints every row twice, once in either side's table, so that each
  side reads its own score and matchpoints. Here is one row in both, abridged to
  the cells that matter:

  ```html
  <h4>N-S</h4> ... <td>620</td><td>2.00</td>
                   <td>1-Ann Alfa-Bob Bravo vs. 4-Gus Charlie-Hal Delta</td>
  <h4>E-W</h4> ... <td>-620</td><td>0.00</td>
                   <td>4-Gus Charlie-Hal Delta vs. 1-Ann Alfa-Bob Bravo</td>
  ```

  The North-South table supplies the row itself. The East-West table is read
  only for the matchpoints it adds, since its score is the same number negated,
  and the two are joined on the pair numbers both name — `1` and `4` above.

  A table leads with its own side's pair, which is why the East-West cell names
  pair 4 first. `_pairs` puts both back into North-South, East-West order before
  the join; without that the tables would meet only where both pairs happen to
  carry the same number.
  """
  tables = _tables(panel)
  north_south = tables.get(Side.NORTH_SOUTH)
  if not north_south:
    # Every board on every capture seen has both tables, so a board with none
    # means the markup has moved and its rows would otherwise be lost silently.
    return issue_reporting.Read(
      (),
      issues=(
        _NO_RESULTS_TABLE.issue(
          'the board has no North-South results table — its rows are dropped'
        ),
      ),
    )

  east_west_matchpoints = {
    key: _number(_column(row, _MATCHPOINTS_COLUMN))
    for row in _rows(tables.get(Side.EAST_WEST))
    if (key := _row_key(_pairs(row, listed_first=Side.EAST_WEST)))
  }
  # Which sides were vulnerable, for the scoring that recovers a row's tricks.
  vulnerability = board_rotation.vulnerability_for_board(board_number)
  vulnerable = vulnerability.vulnerable_sides

  results: list[TravellerResult] = []
  for row in _rows(north_south):
    # Read once and used twice: to name the row's pairs, and as the key the
    # East-West table's matchpoints are joined on.
    pairs = _pairs(row, listed_first=Side.NORTH_SOUTH)
    key = _row_key(pairs)
    results.append(
      _result(
        row,
        pairs=pairs,
        section=section,
        vulnerable=vulnerable,
        east_west_matchpoints=(east_west_matchpoints.get(key) if key else None),
      )
    )
  # Every failure a row can hold is reported on the row itself, which keeps the
  # pairs and the score beside whatever could not be read from them.
  return issue_reporting.Read(tuple(results))


def _tables(panel: bs4.Tag) -> Mapping[Side, bs4.Tag]:
  """The board's two results tables, by the side each is stated from.

  The tables sit beside the panel rather than inside it, in the other half of
  the row the two share, and each is introduced by a heading naming its side.
  """
  row = panel.find_parent('div', class_='row')
  if not row:
    return {}

  found: dict[Side, bs4.Tag] = {}
  for table in row.find_all('table', class_='board-results-table'):
    heading = table.find_previous(['h4', 'h3'])
    side = _TABLE_SIDES.get(_flattened(heading)) if heading else None
    if side and side not in found:
      found[side] = table
  return found


def _rows(table: bs4.Tag | None) -> Sequence[bs4.Tag]:
  """A results table's data rows."""
  if not table:
    return ()
  body = table.find('tbody') or table
  return body.find_all('tr', recursive=False)


def _column(row: bs4.Tag, index: int) -> str:
  """One cell of a results row, by the column's position."""
  cells = row.find_all('td', recursive=False)
  return _flattened(cells[index]) if index < len(cells) else ''


@dataclasses.dataclass(frozen=True)
class _RowKey:
  """The two pair numbers that identify the same row in either table.

  A board's two results tables print the same set of rows from opposite sides,
  so the pair of numbers is what joins a row to its East-West matchpoints.
  """

  north_south: str
  east_west: str


def _row_key(pairs: Sequence[_RowPair]) -> _RowKey | None:
  """The join key for a row, or None where it did not name both pairs.

  A row naming fewer than two pairs has nothing to join on. None rather than a
  blank key is what keeps two such rows, one in either table, from matching each
  other and trading matchpoints they never shared.
  """
  if len(pairs) != 2:
    return None
  return _RowKey(north_south=pairs[0].number, east_west=pairs[1].number)


def _pairs(row: bs4.Tag, *, listed_first: Side) -> Sequence[_RowPair]:
  """Each pair the row names, as its number and its players.

  The cell names one pair, then `vs.`, then the other. A pair's number is loose
  text and each of its players sits in a span of their own, so the names are
  taken from those spans rather than by splitting the text on the hyphens
  between them — a player whose own name is hyphenated (`Juliett-Kilo Lima`)
  would otherwise split in two.

  A table names its own side's pair first, so which pair leads the cell says
  nothing about which side it sat. `listed_first` names the side of the table
  this row came out of, and the two pairs are returned in North-South, East-West
  order either way.
  """
  cells = row.find_all('td', recursive=False)
  if len(cells) <= _PAIRS_COLUMN:
    return ()

  found: list[_MutableRowPair] = []
  for element in cells[_PAIRS_COLUMN].descendants:
    if isinstance(element, bs4.Tag):
      if 'name' in (element.get('class') or []) and found:
        found[-1].names.append(_flattened(element))
      continue
    # A pair number is loose text closing with the hyphen that leads into its
    # players' spans, so it opens a new pair rather than joining the last one.
    match = _PAIR_NUMBER_PATTERN.search(str(element))
    if match:
      found.append(_MutableRowPair(number=match.group('number')))

  if len(found) == 2 and listed_first == Side.EAST_WEST:
    found.reverse()
  return [
    _RowPair(number=pair.number, names=tuple(pair.names)) for pair in found
  ]


def _result(
  row: bs4.Tag,
  *,
  pairs: Sequence[_RowPair],
  section: str | None,
  vulnerable: frozenset[Side],
  east_west_matchpoints: float | None,
) -> TravellerResult:
  """One traveller row: who sat, what they played, and how it scored."""
  printed_score = _column(row, _SCORE_COLUMN)
  is_passed_out = printed_score.strip().upper() == _PASSOUT
  # A passed-out board is written in the score column, not the contract one,
  # which is left blank as it is for a board nobody played. The bridge score for
  # a passout is zero, so the returned score is zero rather than absent.
  score = 0 if is_passed_out else _integer(printed_score)
  resolution = (
    issue_reporting.Read[Resolution | None](Passout())
    if is_passed_out
    else _resolution(row, score=score, vulnerable=vulnerable)
  )
  return TravellerResult(
    north_south=_pair(
      pairs, position=0, side=Side.NORTH_SOUTH, section=section
    ),
    east_west=_pair(pairs, position=1, side=Side.EAST_WEST, section=section),
    resolution=resolution.value,
    score=score,
    north_south_matchpoints=_number(_column(row, _MATCHPOINTS_COLUMN)),
    east_west_matchpoints=east_west_matchpoints,
    issues=resolution.issues,
  )


def _pair(
  pairs: Sequence[_RowPair],
  *,
  position: int,
  side: Side,
  section: str | None,
) -> PairIdentity:
  """One side of a traveller row."""
  # A row that named no pair in this position still belongs in the record, so
  # the missing side is an empty identity rather than a dropped row.
  found = pairs[position] if position < len(pairs) else _RowPair('', ())
  return PairIdentity(
    number=found.number, side=side, section=section, names=found.names
  )


def _resolution(
  row: bs4.Tag, *, score: int | None, vulnerable: frozenset[Side]
) -> issue_reporting.Read[Resolution | None]:
  """What a row's contract resolved to, or None when it records none.

  A row the page has no result for leaves its contract and declarer cells blank
  and writes `NS` where the score goes, carrying zero matchpoints beside it. The
  captured sessions hold such rows only on their opening and closing boards,
  which is where a pair runs out of time to play one. A passed-out board leaves
  the same two cells blank, but writes `PASS` in the score column, and is
  resolved before this is reached.

  The trick count is not published, so it is recovered from the score: for a
  given contract and vulnerability every extra trick is worth strictly more, so
  the score identifies the result uniquely (see `scoring`).
  """
  contract = _column(row, _CONTRACT_COLUMN).replace(' ', '')
  match = _CONTRACT_PATTERN.fullmatch(contract)
  declarer = _column(row, _DECLARER_COLUMN).strip().upper()
  if not match or declarer not in tuple(Direction) or score is None:
    return issue_reporting.Read(None)

  seat = Direction(declarer)
  side = Side.NORTH_SOUTH if seat in Side.NORTH_SOUTH.seats else Side.EAST_WEST
  level = int(match.group('level'))
  strain = notation.STRAIN_BY_LETTER[match.group('strain').upper()]
  penalty = notation.PENALTY_BY_MARK_COUNT[len(match.group('penalty'))]

  try:
    tricks_taken = scoring.tricks_taken_from_score(
      level=level,
      strain=strain,
      penalty=penalty,
      # The published score is stated from North-South, and scoring works from
      # declarer's own side.
      score=score if side == Side.NORTH_SOUTH else -score,
      is_declarer_vulnerable=side in vulnerable,
    )
  except scoring.UnscorableResultError:
    # The contract, the score, and the vulnerability disagree with each other,
    # so no trick count can be recovered. The row keeps its pairs and its score.
    return issue_reporting.Read(
      None,
      issues=(
        _UNSCORABLE_RESULT.issue(
          f'no result of {contract} by {declarer} scores {score} — the row is '
          f'kept without a contract'
        ),
      ),
    )

  return issue_reporting.Read(
    PlayedContract(
      contract=Contract(
        level=level, strain=strain, declarer=seat, penalty=penalty
      ),
      result=Result(tricks_taken=tricks_taken),
    )
  )


def _integer(value: str) -> int | None:
  """A numeric cell as a whole number, or None when it holds something else."""
  try:
    return int(value.replace(',', '').strip())
  except ValueError:
    return None


def _number(value: str) -> float | None:
  """A numeric cell as a number, or None when it holds something else."""
  try:
    return float(value.strip())
  except ValueError:
    return None
