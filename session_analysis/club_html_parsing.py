# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Read a Palo Alto club game's published HTML into a traveller.

BridgeComposer renders every club game to HTML, and unlike the PBN it is
published for nearly every game — so this is the club parser that has to exist,
with the PBN an easier path where it happens to be there (see travellers.md
`#club-format`).

The club's directors publish under two filename prefixes, `R` and `C`, and the
two differ only in presentation: the score tables are identical, `R`
additionally prints the par contract where `C` prints the par score alone.
Neither difference needs a branch here, because both are read through the score
table's own class rather than through the board container, whose class attribute
`C` omits.

Reading through a real HTML parser also absorbs the difference between a file
fetched directly and the same file saved from a browser — attribute quoting,
entity decoding, and inserted `tbody` elements are all the browser's doing, and
none of them survive into the tree. What no parser can absorb is that the two
variants nest a board differently: `R` wraps a board's diagram, analysis and
score table in its container, while `C` writes that container as an empty
element and lets the same parts follow it as siblings. So a board's parts are
gathered by document order rather than by containment.

Suits are printed as glyphs, which fold to their strain letters as each cell is
read — so every pattern here spells plain ASCII.
"""

import dataclasses
import datetime
import re
from collections.abc import Iterator, Mapping, Sequence

import bs4

from session_analysis import glyphs, issue_reporting, notation
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Side,
  Strain,
)
from session_analysis.models import (
  Deal,
  Issue,
  PairIdentity,
  Passout,
  PlayedContract,
  Resolution,
  Result,
)
from session_analysis.notation import BOOK
from session_analysis.travellers import (
  DoubleDummyTricks,
  Par,
  Traveller,
  TravellerBoard,
  TravellerResult,
  TravellerSource,
)

# The board container's id, which is the only place a board states its own
# number in markup rather than in a comment.
_BOARD_ID_PATTERN = re.compile(r'^Board(?P<number>\d+)$')

# The four hands of a diagram, in the order the markup lays them out: the top
# hand, then the left and right of the middle row, then the bottom.
_DIAGRAM_SEATS = (
  Direction.NORTH,
  Direction.WEST,
  Direction.EAST,
  Direction.SOUTH,
)

# The board's printed dealer and vulnerability labels, e.g. `North Deals` and
# `None Vul`. Both are checked against the schedule rather than stored.
_DEALER_PATTERN = re.compile(r'(?P<dealer>North|East|South|West)\s+Deals')
_VULNERABILITY_PATTERN = re.compile(r'(?P<vulnerability>\S+)\s+Vul')

# What the club's markup writes where the patterns below spell ASCII: each
# suit's own symbol, a Unicode minus sign for a negative number, and a
# multiplication sign for a doubling. All fold to their stand-ins as every cell
# is read (see `_flattened`), so the patterns spell only the ASCII forms. Named
# by code point rather than as literals, as `glyphs` does for the dashes — the
# suit symbols especially are hard to tell apart at a glance and awkward to grep
# for.
_ASCII_STAND_INS: Mapping[int, str] = {
  **dict.fromkeys((ord(dash) for dash in glyphs.DASHES), '-'),
  0x00D7: 'x',  # multiplication sign, written for a doubling
  0x2660: Strain.SPADES.value,
  0x2665: Strain.HEARTS.value,
  0x2666: Strain.DIAMONDS.value,
  0x2663: Strain.CLUBS.value,
}

# BridgeComposer prints a suit in a span of its own, so `4S` reaches a reader as
# two elements that `_flattened` separates. The seam absorbs that where the
# pattern reads the paragraph a piece at a time; where a whole contract is read
# at once, `notation.normalize` takes the spacing out instead.
_SEAM = r'\s*'

# A makeable contract in the double-dummy list, e.g. `N 4S`, `NS 2D`, `W 6D`.
# Notrump is spelled `N` here, which is also how a seat is spelled — the two are
# told apart by position, the seat coming before the level.
_MAKEABLE_PATTERN = re.compile(
  notation.DECLARER_PATTERN
  + _SEAM
  + notation.LEVEL_PATTERN
  + _SEAM
  + notation.STRAIN_PATTERN
)

# The par line, e.g. `Par +420: N 4S=` in the `R` variant and `Par +460` in the
# `C` one, which states the score alone.
_PAR_PATTERN = re.compile(
  r"""
  Par\s*(?P<score>[+-]\s*\d+)
  (?:\s*:\s*(?P<contract>.+))?
  """,
  re.VERBOSE,
)

# One par contract, e.g. `N 4S=` or `EW 6D-5`, read from a statement the spacing
# has been taken out of — so `N 4 S=` and `N4S=` are one shape by the time this
# sees them.
_PAR_CONTRACT_PATTERN = re.compile(
  notation.DECLARER_PATTERN
  + notation.CONTRACT_PATTERN
  + notation.RESULT_PATTERN,
  re.IGNORECASE,
)


# A pair as a score table names it: an optional section letter, the pair number,
# then the players' surnames — `4-Alfa-Bravo`, `A9-Charlie-Delta`.
_PAIR_PATTERN = re.compile(
  r'(?P<section>[A-Za-z]*)(?P<number>\d+)-(?P<names>.*)'
)

# The section a full-width row introduces above the rows belonging to it.
_SECTION_ROW_PATTERN = re.compile(r'Section\s+(?P<name>\S+)')

# A line break inside the double-dummy paragraph, whose lines are `br` elements
# rather than newline characters.
_LINE_BREAK_PATTERN = re.compile(r'<br\s*/?>')

# The standings recap's own section heading, e.g. `Section  P North-South`, and
# the side it introduces.
_RECAP_SECTION_PATTERN = re.compile(
  r'Section\s+(?P<name>\S+)\s+(?P<side>North-South|East-West)'
)
_RECAP_SIDES: Mapping[str, Side] = {
  'North-South': Side.NORTH_SOUTH,
  'East-West': Side.EAST_WEST,
}

# The date the recap prints in its title line, e.g. `July 14, 2026`.
_RECAP_DATE_PATTERN = re.compile(
  r'(?P<month>[A-Z][a-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})'
)
_RECAP_DATE_FORMAT = '%B %d %Y'

# Columns in the recap are separated by two or more spaces. Demanding two is
# what keeps a two-word name from splitting and a one-space gap from joining two
# columns.
_RECAP_COLUMN_SEPARATOR = re.compile(r'\s{2,}')

# The separator between the two players of a recap pair. Spaces on both sides
# are what distinguish it from the hyphen inside a surname.
_RECAP_NAME_SEPARATOR = ' - '

# What a score table writes in the contract and score columns of a board that
# was passed out.
_PASSOUT = 'pass'


class _ClubHtmlFormatError(ValueError):
  """A cell this capture filled held something the format does not allow.

  Raised by the readers that sit below the level knowing what their own failure
  costs, and caught at the row or board it came from, so nothing raised here
  leaves the module. A section the file simply does not render — the `C`
  variant's absent par contract, say — is not this, and yields a traveller with
  that field empty and no issue at all.
  """


# Every kind of thing this parser can fail to read, ranked by the shared ladder
# in travellers.md `#issue-reporting`.
_NO_BOARDS = issue_reporting.Failure('no_boards', IssueSeverity.HIGH, 'boards')
_NO_SCORE_TABLE = issue_reporting.Failure(
  'no_score_table', IssueSeverity.HIGH, 'results'
)
_UNREADABLE_DEAL = issue_reporting.Failure(
  'unreadable_deal', IssueSeverity.MEDIUM, 'deal'
)
_UNREADABLE_CONTRACT = issue_reporting.Failure(
  'unreadable_contract', IssueSeverity.MEDIUM, 'resolution'
)
_UNREADABLE_PAR_CONTRACT = issue_reporting.Failure(
  'unreadable_par_contract', IssueSeverity.LOW, 'par'
)

# The pair cells are the one failure whose field depends on which side it was
# read for, so the failure is spelled once per side rather than once for both.
_UNREADABLE_PAIR: Mapping[Side, issue_reporting.Failure] = {
  Side.NORTH_SOUTH: issue_reporting.Failure(
    'unreadable_pair', IssueSeverity.MEDIUM, 'north_south'
  ),
  Side.EAST_WEST: issue_reporting.Failure(
    'unreadable_pair', IssueSeverity.MEDIUM, 'east_west'
  ),
}


def parse_club_html(text: str, *, reference: str) -> Traveller:
  """Return the traveller a club HTML capture describes.

  Nothing is refused. A capture holding no game comes back as a traveller
  carrying an issue rather than as a raised error — a capture that yielded
  nothing is itself worth recording.

  Args:
    text: the capture's whole contents, fetched or browser-saved.
    reference: how the capture is identified afterwards — the path it was saved
      to, or the URL it came from. Recorded on the traveller.
  """
  soup = bs4.BeautifulSoup(text, 'html.parser')
  standings = _Standings.read(soup)

  boards = tuple(
    _board(markup, standings=standings) for markup in _board_markup(soup)
  )
  title = soup.find('title')
  return Traveller(
    source=TravellerSource.CLUB_HTML,
    reference=reference,
    event=title.get_text(strip=True) if title else '',
    date=standings.date,
    boards=boards,
    issues=() if boards else (_NO_BOARDS.issue('the capture holds no boards'),),
  )


@dataclasses.dataclass(frozen=True)
class _PairKey:
  """What it takes to name one pair: its section, its side, and its number.

  A pair number is unique only within its section and side — the same number
  names a different pair on the movement's other side, and again in the next
  section.
  """

  section: str | None
  side: Side
  number: str


class _Standings:
  """The recap's pair standings: who each pair was, in full.

  A score table names a pair by surnames alone. The recap that both variants
  embed names the same pair in full, so it is read once and every row looks its
  pair up here.
  """

  def __init__(
    self,
    *,
    names: Mapping[_PairKey, tuple[str, ...]],
    date: datetime.date | None,
  ) -> None:
    self._names = names
    self.date = date

  @classmethod
  def read(cls, soup: bs4.BeautifulSoup) -> '_Standings':
    """Read the standings out of the capture's recap block.

    A capture with no recap yields empty standings rather than an error: the
    per-board rows stand on their own, only with surnames in place of full
    names.
    """
    recap = soup.find(id='bcrecap')
    if not recap:
      return cls(names={}, date=None)

    names: dict[_PairKey, tuple[str, ...]] = {}
    date: datetime.date | None = None
    section: str | None = None
    side: Side | None = None

    for line in recap.get_text().splitlines():
      if date is None:
        date = _recap_date(line)

      heading = _RECAP_SECTION_PATTERN.search(line)
      if heading:
        section = heading.group('name')
        side = _RECAP_SIDES[heading.group('side')]
        continue

      if not side:
        continue
      entry = _recap_pair(line)
      if entry:
        number, players = entry
        names[_PairKey(section=section, side=side, number=number)] = players

    return cls(names=names, date=date)

  def players(
    self, *, section: str | None, side: Side, number: str
  ) -> tuple[str, ...] | None:
    """The pair's full names, or None when the recap does not name them.

    A single-section game prints no section letter on its rows but still names
    one in the recap, so a row that carries none falls back to whichever section
    the recap recorded that pair number under.
    """
    found = self._names.get(_PairKey(section=section, side=side, number=number))
    if found or section:
      return found
    # TODO: a multi-section game whose rows printed no section letter would take
    # another section's names here, with nothing said. No capture does that, so
    # fixing this waits for a repro case seen in the wild.
    return next(
      (
        players
        for key, players in self._names.items()
        if key.side == side and key.number == number
      ),
      None,
    )


def _recap_date(line: str) -> datetime.date | None:
  """The date the recap's title line prints, if this is that line."""
  match = _RECAP_DATE_PATTERN.search(line)
  if not match:
    return None
  spelled = f'{match.group("month")} {match.group("day")} {match.group("year")}'
  try:
    return datetime.datetime.strptime(spelled, _RECAP_DATE_FORMAT).date()
  except ValueError:
    return None


def _recap_pair(line: str) -> tuple[str, tuple[str, ...]] | None:
  """A standings row's pair number and full names, or None for other lines.

  The recap is fixed-width text whose columns are two or more spaces apart. A
  standings row is the one shape that opens with a pair number and closes with
  two names joined by a spaced hyphen — the spaces being what tells that
  separator apart from the hyphen inside a surname.
  """
  columns = [
    column for column in _RECAP_COLUMN_SEPARATOR.split(line.strip()) if column
  ]
  if len(columns) < 2 or not columns[0].isdigit():
    return None
  if _RECAP_NAME_SEPARATOR not in columns[-1]:
    return None
  players = tuple(
    name.strip() for name in columns[-1].split(_RECAP_NAME_SEPARATOR)
  )
  return columns[0], players


class _BoardMarkup:
  """The elements one board's markup is spread across, in document order."""

  def __init__(self, number: int) -> None:
    self.number = number
    self.hands: list[bs4.Tag] = []
    self.analysis: bs4.Tag | None = None
    self.score_table: bs4.Tag | None = None


def _board_markup(soup: bs4.BeautifulSoup) -> Iterator[_BoardMarkup]:
  """Group the capture's board markup by board, in document order.

  Containment cannot be relied on: the `R` variant wraps a board's parts in its
  container, while the `C` variant writes that container as an empty element and
  leaves the same parts outside it. Document order is what the two variants do
  agree on — a board's diagram, analysis, and score table all follow its
  container and precede the next one.
  """
  current: _BoardMarkup | None = None
  for element in soup.find_all(_is_board_element):
    number = _board_number(element)
    if number is not None:
      if current:
        yield current
      current = _BoardMarkup(number)
      continue
    if not current:
      # A diagram or score table ahead of the first board container states no
      # board of its own. No capture prints one; passing it over is what keeps
      # such markup from joining the board that opens after it.
      continue
    if element.name == 'p':
      current.analysis = element
    elif _has_class(element, 'bchand'):
      current.hands.append(element)
    else:
      current.score_table = element
  if current:
    yield current


def _is_board_element(element: object) -> bool:
  """Whether an element is one of the four that make up a board's markup."""
  if not isinstance(element, bs4.Tag):
    return False
  if element.name == 'div':
    return _board_number(element) is not None
  if element.name == 'table':
    return _has_class(element, 'bchand') or _has_class(element, 'bcst')
  return element.name == 'p' and _has_class(element, 'bcdda')


def _board_number(element: bs4.Tag) -> int | None:
  """The board number a container's id states, or None if it states none."""
  match = _BOARD_ID_PATTERN.match(str(element.get('id') or ''))
  return int(match.group('number')) if match else None


def _has_class(element: bs4.Tag, name: str) -> bool:
  """Whether an element carries a CSS class."""
  return name in _classes(element)


def _classes(element: bs4.Tag) -> Sequence[str]:
  """The CSS classes an element carries, as a list even when it carries none."""
  classes = element.get('class')
  return classes if isinstance(classes, list) else []


def _board(markup: _BoardMarkup, *, standings: _Standings) -> TravellerBoard:
  """Read one board — its deal, its double-dummy analysis, and its rows.

  Each part is read on its own and reports its own failures, so an unreadable
  deal costs the deal alone and leaves the rows the board was played at intact.
  """
  labels = _board_labels(markup)

  # Read once and handed to both readers below: the paragraph's lines are `br`
  # elements rather than characters, so recovering them means re-parsing its
  # markup.
  analysis = _analysis_lines(markup.analysis)

  deal = _deal(markup.hands)
  double_dummy_tricks = _makeable_tricks(analysis)
  par = _par(analysis, double_dummy_tricks=double_dummy_tricks)
  results = _results(markup.score_table, standings=standings)

  return TravellerBoard(
    number=markup.number,
    deal=deal.value,
    double_dummy_tricks=double_dummy_tricks,
    par=par.value,
    results=results.value,
    issues=(
      *deal.issues,
      *par.issues,
      *results.issues,
      *notation.board_schedule_issues(
        board_number=markup.number,
        dealer=labels.dealer,
        vulnerability=labels.vulnerability,
      ),
    ),
  )


@dataclasses.dataclass(frozen=True)
class _BoardLabels:
  """What a board's diagram prints beside the cards, where it prints anything.

  Both are read only to be checked against the schedule the board number fixes —
  neither is stored, because both follow from that number.
  """

  dealer: Direction | None = None
  vulnerability: str | None = None


def _board_labels(markup: _BoardMarkup) -> _BoardLabels:
  """The dealer and vulnerability labels a board's diagram prints."""
  if not markup.hands:
    return _BoardLabels()
  # The labels sit in the diagram beside the top hand, so they are reachable
  # from it without depending on the container that failed to hold it.
  diagram = markup.hands[0].find_parent('table')
  if not diagram:
    return _BoardLabels()

  text = _flattened(diagram)
  dealer = _DEALER_PATTERN.search(text)
  vulnerability = _VULNERABILITY_PATTERN.search(text)
  return _BoardLabels(
    dealer=Direction(dealer.group('dealer')[0]) if dealer else None,
    vulnerability=(
      vulnerability.group('vulnerability') if vulnerability else None
    ),
  )


def _flattened(element: bs4.Tag) -> str:
  """An element's text, normalized to the spelling the patterns here expect.

  Two normalizations, both applied here so that no caller has to remember them.
  Every run of whitespace collapses to one space — BridgeComposer separates
  parts with non-breaking and thin spaces, which would otherwise leave each
  reader matching characters that vary by cell. And the two typographic glyphs
  it writes, the minus sign and the multiplication sign, fold to their ASCII
  stand-ins.
  """
  # `get_text`'s argument is a separator placed between adjacent nodes, and it
  # defaults to none — which would weld the diagram's `North Deals` and `None
  # Vul` cells into `North DealsNone Vul`, leaving the vulnerability pattern to
  # read `DealsNone`.
  return ' '.join(element.get_text(' ').translate(_ASCII_STAND_INS).split())


def _deal(hands: Sequence[bs4.Tag]) -> issue_reporting.Read[Deal | None]:
  """The deal the four hand diagrams state, or None when a board prints none.

  A board printing some hands but not four is reported rather than passed over:
  every capture seen prints four, so a different count means the markup has
  moved and a deal is going missing. A board printing none at all is an ordinary
  capture with no hand records, and carries no issue.

  A deal is four whole hands or it is nothing — a partial one would report cards
  nobody held — so anything unreadable within a deal costs the whole deal.
  """
  if not hands:
    return issue_reporting.Read(None)
  if len(hands) != len(_DIAGRAM_SEATS):
    return issue_reporting.Read(
      None,
      issues=(
        _UNREADABLE_DEAL.issue(
          f'board prints {len(hands)} hand diagrams, not '
          f'{len(_DIAGRAM_SEATS)} — its deal is dropped'
        ),
      ),
    )

  try:
    return issue_reporting.Read(
      notation.deal_from_hands(
        {
          seat: notation.hand_from_holdings(_holdings(hand))
          for seat, hand in zip(_DIAGRAM_SEATS, hands, strict=True)
        }
      )
    )
  except notation.NotationError as error:
    # An unreadable rank, or a suit the diagram left out.
    return issue_reporting.Read(
      None, issues=(_UNREADABLE_DEAL.issue(str(error)),)
    )


def _holdings(hand: bs4.Tag) -> Sequence[str]:
  """One hand's four suit holdings, highest suit first.

  A hand diagram gives each suit a row of two cells — the suit's glyph, by now
  replaced with its letter, and the ranks held in it. A suit the player was
  dealt none of may be printed as an empty row or left out of the diagram
  entirely, so the rows are read into the four suits by name rather than by
  position.
  """
  by_suit: dict[str, str] = {}
  for row in hand.find_all('tr'):
    cells = row.find_all('td')
    if len(cells) < 2:
      continue
    suit_letter = _flattened(cells[0]).upper()
    by_suit[suit_letter] = cells[1].get_text(strip=True)
  return tuple(
    by_suit.get(suit.value, '') for suit in notation.SUITS_HIGH_TO_LOW
  )


def _analysis_lines(analysis: bs4.Tag | None) -> Sequence[str]:
  """The double-dummy paragraph's lines, up to the opening-lead notes.

  The paragraph holds the makeable-contract list and par, then a blank line,
  then a note per opening lead. Only what precedes the blank line is read; the
  lead notes are analysis the traveller does not carry.
  """
  if not analysis:
    return ()
  # The paragraph's line breaks are `br` elements rather than characters, so its
  # markup is split on those; the empty line that opens the lead notes ends it.
  lines: list[str] = []
  for line in _LINE_BREAK_PATTERN.split(analysis.decode()):
    text = _flattened(bs4.BeautifulSoup(line, 'html.parser'))
    if not text:
      break
    lines.append(text)
  return tuple(lines)


def _makeable_tricks(analysis: Sequence[str]) -> DoubleDummyTricks | None:
  """The double-dummy table the makeable-contract list states.

  The club lists only the contracts that make, so every seat and strain it
  leaves out takes fewer than seven tricks without saying how many. Those cells
  stay `None`, since `None` is the honest reading of a count the list never
  gave.
  """
  if not analysis:
    return None

  tricks: dict[Direction, dict[Strain, int | None]] = {
    seat: dict.fromkeys(notation.STRAINS_LOW_TO_HIGH) for seat in Direction
  }
  # The list runs to the start of par, wherever that falls: the `C` variant
  # prints par on the same line as the contracts, and a list long enough to wrap
  # carries on past the first line. So the lines are joined and cut at par
  # rather than only the first one being read.
  makeable, _, _ = ' '.join(analysis).partition('Par')
  for match in _MAKEABLE_PATTERN.finditer(makeable):
    declarer = notation.declarer_from_token(match.group('declarer'))
    seats = declarer.seats if isinstance(declarer, Side) else (declarer,)
    strain = notation.STRAIN_BY_LETTER[match.group('strain')]
    for seat in seats:
      tricks[seat][strain] = int(match.group('level')) + BOOK
  return tricks


def _par(
  analysis: Sequence[str], *, double_dummy_tricks: DoubleDummyTricks | None
) -> issue_reporting.Read[Par | None]:
  """The par the analysis paragraph states.

  The `R` variant states the score and the contract achieving it; the `C`
  variant states the score alone, and a score alone yields a par with no
  contracts rather than no par — the score is the part both variants agree on
  and the part reconciliation compares. So an unreadable contract costs that
  contract while the score stands, exactly as the `C` variant does by design.
  """
  match = _PAR_PATTERN.search(' '.join(analysis))
  if not match:
    return issue_reporting.Read(None)

  resolutions: list[Resolution] = []
  issues: list[Issue] = []
  for statement in (match.group('contract') or '').split(';'):
    contract = _PAR_CONTRACT_PATTERN.search(notation.normalize(statement))
    if not contract:
      continue
    level = int(contract.group('level'))
    try:
      resolutions.extend(
        notation.par_contracts(
          level=level,
          strain=notation.STRAIN_BY_LETTER[contract.group('strain')],
          penalty=notation.PENALTY_BY_MARK_COUNT[
            len(contract.group('penalty'))
          ],
          declarer=notation.declarer_from_token(contract.group('declarer')),
          stated_tricks=notation.tricks_taken_from_par_result(
            contract.group('result') or '', level
          ),
          double_dummy_tricks=double_dummy_tricks,
        )
      )
    except notation.NotationError as error:
      # An unreadable result, or one the statement omits with no makeable-
      # contract list to recover it from.
      issues.append(_UNREADABLE_PAR_CONTRACT.issue(str(error)))

  return issue_reporting.Read(
    Par(score=_signed(match.group('score')), resolutions=tuple(resolutions)),
    issues=tuple(issues),
  )


def _signed(value: str) -> int:
  """An integer that may carry a sign and the space the markup pads it with."""
  return int(value.replace(' ', ''))


def _results(
  score_table: bs4.Tag | None, *, standings: _Standings
) -> issue_reporting.Read[tuple[TravellerResult, ...]]:
  """The traveller rows a board's score table holds.

  A multi-section game introduces each section with a full-width row above the
  rows belonging to it, so the section a row sat in is carried forward from the
  last such heading — except where the pair cells state it themselves, which
  they do in exactly the games that have more than one section.
  """
  if not score_table:
    # Every board of every capture seen prints one, so a board with none means
    # the markup has moved — and a whole board's play would otherwise go missing
    # without a word.
    return issue_reporting.Read(
      (),
      issues=(
        _NO_SCORE_TABLE.issue(
          'the board prints no score table — its rows are dropped'
        ),
      ),
    )

  results: list[TravellerResult] = []
  section: str | None = None
  for row in score_table.find_all('tr'):
    heading = _section_heading(row)
    if heading:
      section = heading
      continue
    if not row.find('td', class_='bcstcontract'):
      continue
    results.append(_result(row, section=section, standings=standings))
  # Past a missing table there is nothing left to report here: every failure a
  # row can hold is reported on the row itself, keeping the pairs and the score
  # beside whatever could not be read from them.
  return issue_reporting.Read(tuple(results))


def _section_heading(row: bs4.Tag) -> str | None:
  """The section a full-width heading row introduces, or None for other rows."""
  cells = row.find_all(['td', 'th'])
  if len(cells) != 1:
    return None
  match = _SECTION_ROW_PATTERN.search(cells[0].get_text(strip=True))
  return match.group('name') if match else None


def _result(
  row: bs4.Tag, *, section: str | None, standings: _Standings
) -> TravellerResult:
  """One traveller row: who sat, what they played, and how it scored."""
  north_south = _pair(
    row, side=Side.NORTH_SOUTH, section=section, standings=standings
  )
  east_west = _pair(
    row, side=Side.EAST_WEST, section=section, standings=standings
  )
  resolution = _resolution(row)
  return TravellerResult(
    north_south=north_south.value,
    east_west=east_west.value,
    resolution=resolution.value,
    score=_score(row),
    north_south_matchpoints=_number(_cell(row, 'bcstmpns')),
    east_west_matchpoints=_number(_cell(row, 'bcstmpew')),
    issues=(*north_south.issues, *east_west.issues, *resolution.issues),
  )


def _cell(row: bs4.Tag, name: str) -> str:
  """A row cell's text, with the whitespace BridgeComposer pads it with gone."""
  cell = row.find('td', class_=name)
  return _flattened(cell).replace(' ', '') if cell else ''


def _pair(
  row: bs4.Tag, *, side: Side, section: str | None, standings: _Standings
) -> issue_reporting.Read[PairIdentity]:
  """One side of a traveller row, with full names when the recap supplies them.

  The row itself gives surnames only. The recap names the same pair in full, so
  it is preferred where it has an entry and the surnames stand in where it does
  not — a pair that played but placed nowhere, or a capture with no recap.

  A cell naming no pair still yields a pair, carrying an empty number: the row's
  other side, its contract, and its score are all still good, and dropping the
  row over one cell would lose them. Only a cell that held something unreadable
  reports — an empty cell is the capture stating no pair, and a row is entitled
  to state none.
  """
  cell = row.find(
    'td', class_=f'bcstpair{"ns" if side == Side.NORTH_SOUTH else "ew"}'
  )
  printed = _flattened(cell) if cell else ''
  match = _PAIR_PATTERN.fullmatch(printed) if printed else None
  if not match:
    # An empty cell is the capture stating no pair, not a failure to read one,
    # so only a cell that held something reports.
    issues = (
      (_UNREADABLE_PAIR[side].issue(f'unreadable pair cell {printed!r}'),)
      if printed
      else ()
    )
    return issue_reporting.Read(
      PairIdentity(number='', side=side, section=section), issues=issues
    )

  number = match.group('number')
  in_section = match.group('section') or section
  surnames = tuple(name for name in match.group('names').split('-') if name)
  return issue_reporting.Read(
    PairIdentity(
      number=number,
      side=side,
      section=in_section,
      names=standings.players(section=in_section, side=side, number=number)
      or surnames,
    )
  )


def _resolution(row: bs4.Tag) -> issue_reporting.Read[Resolution | None]:
  """What a row's contract cell resolved to, or None when it names none."""
  written = _cell(row, 'bcstcontract')
  if written.lower() == _PASSOUT:
    return issue_reporting.Read(Passout())

  declarer = _cell(row, 'bcstdeclarer')
  made = _cell(row, 'bcstmade')
  contract = notation.parse_contract(
    written, declarer=notation.parse_seat(declarer)
  )
  if not contract or not made:
    # A row naming no contract at all is a legitimate state — a board never
    # played, or one the director adjusted — so only a row that named one and
    # then could not be read is worth reporting.
    if not written:
      return issue_reporting.Read(None)
    return _unreadable_contract(written, declarer, made)

  try:
    tricks_taken = _tricks_taken(made, contract.level)
  except _ClubHtmlFormatError:
    # A `Made` column holding neither form.
    return _unreadable_contract(written, declarer, made)

  return issue_reporting.Read(
    PlayedContract(contract=contract, result=Result(tricks_taken=tricks_taken))
  )


def _unreadable_contract(
  contract: str, declarer: str, made: str
) -> issue_reporting.Read[Resolution | None]:
  """No resolution, and the three cells that were supposed to give one."""
  return issue_reporting.Read(
    None,
    issues=(
      _UNREADABLE_CONTRACT.issue(
        f'unreadable contract {contract!r} by {declarer!r} made {made!r}'
      ),
    ),
  )


def _tricks_taken(made: str, level: int) -> int:
  """The trick count the `Made` column states.

  The column is written from the contract's point of view in two different ways:
  a contract that came home shows the level it made, so `5` on a four-level
  contract is eleven tricks; one that did not shows how far down it went.

  Raises:
    _ClubHtmlFormatError: if the column holds neither form.
  """
  if made.startswith('-') and made[1:].isdigit():
    return level + BOOK - int(made[1:])
  if not made.isdigit():
    raise _ClubHtmlFormatError(f'unreadable made column: {made!r}')
  return int(made) + BOOK


def _score(row: bs4.Tag) -> int | None:
  """A row's score, from North-South's perspective.

  The table prints the score in whichever side's column it is positive for and
  leaves the other blank, so the two columns collapse to one signed number. A
  passed-out board scores nothing for either side, and the table writes that
  empty score as `Pass` in the score column rather than as a zero.
  """
  north_south = _cell(row, 'bcstscorens')
  if north_south.lower() == _PASSOUT:
    return 0
  # Read as a signed integer rather than a bare run of digits: the table has not
  # been seen to print a negative, but the PBN's own reader accepts one, and the
  # two must not disagree about a game published in both forms.
  signed = _signed_or_none(north_south)
  if signed is not None:
    return signed
  signed = _signed_or_none(_cell(row, 'bcstscoreew'))
  return -signed if signed is not None else None


def _signed_or_none(value: str) -> int | None:
  """A score cell as a whole number, or None when the cell holds no number."""
  try:
    return _signed(value)
  except ValueError:
    return None


def _number(value: str) -> float | None:
  """A numeric cell's value, or None when the cell is empty."""
  try:
    return float(value)
  except ValueError:
    return None
