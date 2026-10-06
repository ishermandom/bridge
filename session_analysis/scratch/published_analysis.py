# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Write a deal's published analysis the way each capture format writes it.

The traveller fixtures carry placeholder names but genuine analysis: their
double-dummy tables, pars, and opening-lead notes are what their own deals
yield. This harness generates that text from a deal, in each capture format's
own notation, and writes it into the fixtures.

Every rule here was inferred from real captures rather than from any
documentation, so `check` comes before `rewrite`: it regenerates the analysis of
every capture in the private tree and compares it with what the source
published, character for character. See this directory's README.md for when and
how to run both.

The solver is reached through `double_dummy_solving`, the project's only seam
onto it — private names included, since that module's spelling of seats,
strains, and deals is the one thing here that must not be restated.
"""

import argparse
import dataclasses
import enum
import html
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import endplay.dds
import endplay.types

from session_analysis import (
  acbl_club_parsing,
  acbl_tournament_parsing,
  board_rotation,
  club_html_parsing,
  club_pbn_parsing,
  scoring,
)
from session_analysis.enums import (
  Direction,
  Penalty,
  Rank,
  Side,
  Strain,
  Suit,
)
from session_analysis.models import CaptureReference, Card, Deal
from session_analysis.private_paths import discover_private_tree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed.double_dummy_solving import (
  _SOLVER_SEATS,
  _SOLVER_STRAINS,
  _written_deal,
  solve_table,
)

_STRAINS_LOW_TO_HIGH = (
  Strain.CLUBS,
  Strain.DIAMONDS,
  Strain.HEARTS,
  Strain.SPADES,
  Strain.NOTRUMP,
)
_STRAINS_HIGH_TO_LOW = tuple(reversed(_STRAINS_LOW_TO_HIGH))
_SUITS_HIGH_TO_LOW = (Suit.SPADES, Suit.HEARTS, Suit.DIAMONDS, Suit.CLUBS)
_RANKS_HIGH_TO_LOW = tuple(reversed(list(Rank)))
_SUIT_OF_STRAIN = {
  Strain.SPADES: Suit.SPADES,
  Strain.HEARTS: Suit.HEARTS,
  Strain.DIAMONDS: Suit.DIAMONDS,
  Strain.CLUBS: Suit.CLUBS,
}

_DEFAULT_FIXTURES = Path(__file__).parent.parent / 'testdata' / 'travellers'
_FIXTURE_REFERENCE = CaptureReference(path='fixture')


# --- solving ------------------------------------------------------------------

_SOLVER_VULNERABILITY = {
  'none': endplay.types.Vul.none,
  'NS': endplay.types.Vul.ns,
  'EW': endplay.types.Vul.ew,
  'both': endplay.types.Vul.both,
}
_STRAIN_FROM_SOLVER = {
  denom: strain for strain, denom in _SOLVER_STRAINS.items()
}
_SEAT_FROM_SOLVER = {player: seat for seat, player in _SOLVER_SEATS.items()}
_SUIT_FROM_SOLVER = {
  'spades': Suit.SPADES,
  'hearts': Suit.HEARTS,
  'diamonds': Suit.DIAMONDS,
  'clubs': Suit.CLUBS,
}
_PENALTY_FROM_SOLVER = {
  endplay.types.Penalty.passed: Penalty.NONE,
  endplay.types.Penalty.doubled: Penalty.DOUBLED,
  endplay.types.Penalty.redoubled: Penalty.REDOUBLED,
}


@dataclasses.dataclass(frozen=True)
class ParContract:
  """One par contract, reached by one seat or by both seats of a side."""

  level: int
  strain: Strain
  penalty: Penalty
  # Tricks against the contract: zero made exactly, positive over, negative
  # down.
  result: int
  seats: tuple[Direction, ...]

  @property
  def doublings(self) -> int:
    """How many times the contract was doubled: none, once, or twice."""
    return {Penalty.NONE: 0, Penalty.DOUBLED: 1, Penalty.REDOUBLED: 2}[
      self.penalty
    ]


@dataclasses.dataclass(frozen=True)
class Par:
  """The par score, from North-South's side, and the contracts reaching it."""

  north_south_score: int
  # Ordered by level, then by strain from clubs up.
  contracts: tuple[ParContract, ...]


def _side_of(seat: Direction) -> Side:
  """The side a seat sits on."""
  return Side.NORTH_SOUTH if seat in Side.NORTH_SOUTH.seats else Side.EAST_WEST


def _seats_name(seats: Sequence[Direction]) -> str:
  """A side's name for both its seats, or one seat's letter."""
  return _side_of(seats[0]).value if len(seats) == 2 else seats[0].value


def _declarer_led_by(leader: Direction) -> Direction:
  """The seat a leader is on lead against: the one to the leader's right."""
  return next(seat for seat in Direction if seat.left_hand_opponent is leader)


def par_of(deal: Deal, board_number: int) -> Par:
  """Par as the solver states it, with a contract's two seats merged."""
  vulnerability = board_rotation.vulnerability_for_board(board_number)
  solved = endplay.dds.par(
    endplay.types.Deal(_written_deal(deal)),
    _SOLVER_VULNERABILITY[vulnerability.value],
    _SOLVER_SEATS[board_rotation.dealer_for_board(board_number)],
  )
  grouped: dict[tuple[int, Strain, Penalty, int], list[Direction]] = {}
  for contract in solved:
    key = (
      int(contract.level),
      _STRAIN_FROM_SOLVER[contract.denom],
      _PENALTY_FROM_SOLVER[contract.penalty],
      int(contract.result),
    )
    grouped.setdefault(key, []).append(_SEAT_FROM_SOLVER[contract.declarer])

  contracts = [
    ParContract(
      level=level,
      strain=strain,
      penalty=penalty,
      result=result,
      seats=tuple(seat for seat in Direction if seat in seats),
    )
    for (level, strain, penalty, result), seats in grouped.items()
  ]
  contracts.sort(
    key=lambda contract: (
      contract.level,
      _STRAINS_LOW_TO_HIGH.index(contract.strain),
    )
  )
  return Par(int(solved.score), tuple(contracts))


def best_leads(
  deal: Deal, leader: Direction, strain: Strain
) -> tuple[int, frozenset[Card]]:
  """The defenders' best trick count on lead, and every card achieving it."""
  position = endplay.types.Deal(_written_deal(deal))
  position.first = _SOLVER_SEATS[leader]
  position.trump = _SOLVER_STRAINS[strain]
  results = [
    (card, int(tricks)) for card, tricks in endplay.dds.solve_board(position)
  ]
  best = max(tricks for _, tricks in results)
  cards = frozenset(
    Card(rank=Rank(card.rank.abbr), suit=_SUIT_FROM_SOLVER[card.suit.name])
    for card, tricks in results
    if tricks == best
  )
  return best, cards


# --- the club's PBN -----------------------------------------------------------

_PBN_STRAIN = {
  Strain.NOTRUMP: 'NT',
  Strain.SPADES: 'S',
  Strain.HEARTS: 'H',
  Strain.DIAMONDS: 'D',
  Strain.CLUBS: 'C',
}
_PBN_SEAT_ORDER = (
  Direction.NORTH,
  Direction.SOUTH,
  Direction.EAST,
  Direction.WEST,
)


def pbn_result_table(deal: Deal) -> str:
  """The `[OptimumResultTable]` tag and its twenty rows."""
  table = solve_table(deal)
  # The count column is as wide as its widest count.
  width = max(
    len(str(table[seat][strain])) for seat in Direction for strain in Strain
  )
  rows = [
    f'{seat} {_PBN_STRAIN[strain]:>2} {table[seat][strain]:>{width}}'
    for seat in _PBN_SEAT_ORDER
    for strain in _STRAINS_HIGH_TO_LOW
  ]
  header = f'[OptimumResultTable "Declarer;Denomination\\2R;Result\\{width}R"]'
  return '\n'.join([header, *rows])


def _result_mark(result: int) -> str:
  """A result as par writes it: `=`, `+1`, `-2`."""
  return '=' if result == 0 else f'{result:+d}'


def pbn_par_tags(deal: Deal, board_number: int) -> str:
  """The `[OptimumScore]` and `[ParContract]` tags."""
  par = par_of(deal, board_number)
  declaring_side = _side_of(par.contracts[0].seats[0])
  # The score is the declaring side's, where every other format gives North-
  # South's.
  score = (
    par.north_south_score
    if declaring_side is Side.NORTH_SOUTH
    else -par.north_south_score
  )
  contracts = '; '.join(
    f'{_seats_name(contract.seats)} {contract.level}'
    f'{"N" if contract.strain is Strain.NOTRUMP else contract.strain}'
    f'{"X" * contract.doublings}{_result_mark(contract.result)}'
    for contract in par.contracts
  )
  return (
    f'[OptimumScore "{declaring_side} {score}"]\n[ParContract "{contracts}"]'
  )


def _pbn_cards(cards: frozenset[Card], suit: Suit) -> str:
  """One suit's cards, high first, or `-` for none."""
  ranks = {card.rank for card in cards if card.suit is suit}
  if not ranks:
    return '-'
  return ''.join(rank for rank in _RANKS_HIGH_TO_LOW if rank in ranks)


def pbn_lead_table(deal: Deal) -> str:
  """The `[OptimumOpeningLeadTable]` tag and its twenty rows.

  Each row gives the defenders' best count with that leader on lead in that
  strain, then the leads achieving it, suit by suit.
  """
  rows = []
  for leader in _PBN_SEAT_ORDER:
    for strain in _STRAINS_HIGH_TO_LOW:
      tricks, cards = best_leads(deal, leader, strain)
      suits = [_pbn_cards(cards, suit) for suit in _SUITS_HIGH_TO_LOW]
      rows.append((leader, strain, tricks, suits))

  # Every column but the last is as wide as its widest entry.
  result_width = max(len(str(tricks)) for _, _, tricks, _ in rows)
  spades, hearts, diamonds = (
    max(len(suits[column]) for _, _, _, suits in rows) for column in range(3)
  )
  header = (
    '[OptimumOpeningLeadTable "Leader;Denomination\\2R;'
    f'Result\\{result_width}R;S\\{spades};H\\{hearts};D\\{diamonds};C"]'
  )
  lines = [
    f'{leader} {_PBN_STRAIN[strain]:>2} {tricks:>{result_width}} '
    f'{suits[0]:<{spades}} {suits[1]:<{hearts}} {suits[2]:<{diamonds}} '
    f'{suits[3]}'
    for leader, strain, tricks, suits in rows
  ]
  return '\n'.join([header, *lines])


# --- the club's BridgeComposer HTML -------------------------------------------

_CLUB_SUIT = {
  Suit.SPADES: '<span class=bcspades>&spades;</span>',
  Suit.HEARTS: '<span class=bchearts>&hearts;</span>',
  Suit.DIAMONDS: '<span class=bcdiams>&diams;</span>',
  Suit.CLUBS: '<span class=bcclubs>&clubs;</span>',
}


def _club_strain(strain: Strain, notrump: str) -> str:
  """A strain as the recap writes it, notrump being spelled per context."""
  if strain is Strain.NOTRUMP:
    return notrump
  return _CLUB_SUIT[_SUIT_OF_STRAIN[strain]]


class ClubStyle(enum.Enum):
  """The two styles of club recap, told apart by how they state par.

  Most recaps put par on a line of its own, naming its contracts, and write a
  ten as `10`. The lagcc recaps instead append the par score to the makeable
  contracts — naming the contracts only for a doubled sacrifice — and write a
  ten as `T`.
  """

  PAR_LINE = enum.auto()
  PAR_SCORE = enum.auto()

  @classmethod
  def of(cls, paragraph: str) -> 'ClubStyle':
    """The style a published analysis paragraph is in."""
    return cls.PAR_LINE if '<br>Par&nbsp;' in paragraph else cls.PAR_SCORE


def _club_ranks(cards: frozenset[Card], style: ClubStyle) -> str:
  """Cards' ranks, high first, with a ten written the style's way."""
  ten = '10' if style is ClubStyle.PAR_LINE else 'T'
  ranks = {card.rank for card in cards}
  return ''.join(
    ten if rank is Rank.TEN else rank
    for rank in _RANKS_HIGH_TO_LOW
    if rank in ranks
  )


def club_makeable(deal: Deal) -> str:
  """The makeable contracts, each followed by `; `, best-scoring first.

  A side's two seats merge into one entry when they make the same level. The
  ranking is by the contract's non-vulnerable score whatever the board's
  vulnerability, ties going to the higher strain.
  """
  table = solve_table(deal)
  entries: list[tuple[int, int, tuple[Direction, ...], int, Strain]] = []
  for strain in Strain:
    for side in (Side.NORTH_SOUTH, Side.EAST_WEST):
      making = {
        seat: table[seat][strain] - 6
        for seat in side.seats
        if table[seat][strain] >= 7
      }
      groups: list[tuple[tuple[Direction, ...], int]]
      if len(making) == 2 and len(set(making.values())) == 1:
        groups = [(side.seats, making[side.seats[0]])]
      else:
        groups = [((seat,), level) for seat, level in making.items()]
      for seats, level in groups:
        score = scoring.score_for_contract(
          level=level,
          strain=strain,
          penalty=Penalty.NONE,
          tricks_taken=level + 6,
          is_declarer_vulnerable=False,
        )
        rank = _STRAINS_HIGH_TO_LOW.index(strain)
        entries.append((score, rank, seats, level, strain))
  entries.sort(key=lambda entry: (-entry[0], entry[1]))
  return ''.join(
    f'{_seats_name(seats)}&nbsp;{level}{_club_strain(strain, "N")}; '
    for _, _, seats, level, strain in entries
  )


def _club_signed(count: int) -> str:
  """A score or result with its sign, minus written as an entity."""
  if count < 0:
    return f'&minus;{-count}'
  return f'+{count}' if count > 0 else '0'


def club_par(deal: Deal, board_number: int, style: ClubStyle) -> str:
  """The par, as `ClubStyle` says each style states it."""
  par = par_of(deal, board_number)
  score = _club_signed(par.north_south_score)
  contracts = '; '.join(
    f'{_seats_name(contract.seats)}&nbsp;{contract.level}'
    f'{_club_strain(contract.strain, "N")}{"&times;" * contract.doublings}'
    f'{"=" if contract.result == 0 else _club_signed(contract.result)}'
    for contract in par.contracts
  )
  if style is ClubStyle.PAR_LINE:
    return f'<br>Par&nbsp;{score}: {contracts}'
  if all(contract.doublings for contract in par.contracts):
    return f'Par&nbsp;{score}: {contracts}'
  return f'Par&nbsp;{score}'


def _describe_leads(
  hand: frozenset[Card], best: frozenset[Card], style: ClubStyle
) -> str:
  """The recap's account of which leads hold declarer to the best count.

  `any card except …` names what to avoid when that is a single card, or a whole
  suit of a hand holding all four; otherwise the good leads are listed suit by
  suit, `any ♠` covering a suit only when every card of two or more is good.
  """
  if best == hand:
    return 'any card'
  excluded = hand - best
  excluded_suits = {card.suit for card in excluded}
  if len(excluded_suits) == 1:
    (suit,) = excluded_suits
    if len(excluded) == 1:
      ranks = _club_ranks(excluded, style)
      return f'any card except {_CLUB_SUIT[suit]}&thinsp;{ranks}'
    holds_every_suit = len({card.suit for card in hand}) == 4
    whole_suit = frozenset(card for card in hand if card.suit is suit)
    if holds_every_suit and excluded == whole_suit:
      return f'any card except a {_CLUB_SUIT[suit]}'

  parts = []
  for suit in _SUITS_HIGH_TO_LOW:
    held = frozenset(card for card in hand if card.suit is suit)
    good = best & held
    if not good:
      continue
    if good == held and len(held) > 1:
      parts.append(f'any {_CLUB_SUIT[suit]}')
    else:
      parts.append(f'{_CLUB_SUIT[suit]}&thinsp;{_club_ranks(good, style)}')
  return '; '.join(parts)


def club_lead_notes(deal: Deal, style: ClubStyle) -> str:
  """`<br><br>`, then a note per declarer and strain that makes something."""
  table = solve_table(deal)
  notes = []
  for leader in Direction:
    declarer = _declarer_led_by(leader)
    for strain in _STRAINS_HIGH_TO_LOW:
      if table[declarer][strain] < 7:
        continue
      _, best = best_leads(deal, leader, strain)
      hand = frozenset(deal.hands[leader].cards)
      notes.append(
        f'{leader} vs {declarer} {_club_strain(strain, "NT")}: '
        f'{_describe_leads(hand, best, style)}'
      )
  return '<br><br>' + '<br>'.join(notes)


def club_paragraph(deal: Deal, board_number: int, style: ClubStyle) -> str:
  """Everything a board's `<p class=bcdda>` holds after its opening line."""
  return (
    club_makeable(deal)
    + club_par(deal, board_number, style)
    + club_lead_notes(deal, style)
  )


# --- ACBL, both surfaces ------------------------------------------------------

_ACBL_STRAIN = {
  Strain.CLUBS: 'C',
  Strain.DIAMONDS: 'D',
  Strain.HEARTS: 'H',
  Strain.SPADES: 'S',
  Strain.NOTRUMP: 'NT',
}


def _merged(values: tuple[int | None, ...]) -> tuple[int | None, ...]:
  """One value where a side's two seats agree, both where they differ."""
  return values[:1] if values[0] == values[1] else values


def _dash(value: int | None) -> str:
  """A seat's value, or `-` for a seat that makes nothing."""
  return '-' if value is None else str(value)


def acbl_line(deal: Deal, side: Side) -> str:
  """The club page's `NS:` or `EW:` line.

  Strains both seats make come first, as levels; the rest follow as trick
  counts. A side straddling seven tricks gets the trick-count cell alone.
  """
  table = solve_table(deal)
  levels, counts = [], []
  for strain in _STRAINS_LOW_TO_HIGH:
    tricks = tuple(table[seat][strain] for seat in side.seats)
    letter = _ACBL_STRAIN[strain]
    if all(count >= 7 for count in tricks):
      made = _merged(tuple(count - 6 for count in tricks))
      levels.append(f'{"/".join(_dash(v) for v in made)}{letter}')
    else:
      counts.append(f'{letter}{"/".join(_dash(v) for v in _merged(tricks))}')
  return f'{side}: ' + ' '.join(levels + counts)


def _acbl_declarer(seats: Sequence[Direction]) -> str:
  """Who declares par; ACBL's pages write North alone as `NT`."""
  name = _seats_name(seats)
  return 'NT' if name == 'N' else name


def acbl_par(deal: Deal, board_number: int) -> str:
  """The club page's par line.

  Making contracts are ordered by tricks and then strain, both descending;
  doubled sacrifices by strain ascending.
  """
  par = par_of(deal, board_number)
  if all(contract.doublings for contract in par.contracts):
    ordered = sorted(
      par.contracts,
      key=lambda contract: _STRAINS_LOW_TO_HIGH.index(contract.strain),
    )
  else:
    ordered = sorted(
      par.contracts,
      key=lambda contract: (
        -(contract.level + contract.result),
        -_STRAINS_LOW_TO_HIGH.index(contract.strain),
      ),
    )
  contracts = '/'.join(
    f'{contract.level}{_ACBL_STRAIN[contract.strain]}'
    f'{"*" * contract.doublings}-{_acbl_declarer(contract.seats)}'
    f'{f"{contract.result:+d}" if contract.result else ""}'
    for contract in ordered
  )
  return f'Par: {par.north_south_score} {contracts}'


class Quoting(enum.StrEnum):
  """How a page quotes its attributes.

  A page as served uses single quotes; one saved from a browser, as the
  tournament fixture is, uses double.
  """

  SERVED = "'"
  BROWSER_SAVED = '"'


_SYMBOL_CLASS = {
  Strain.SPADES: 'spades',
  Strain.HEARTS: 'hearts',
  Strain.DIAMONDS: 'diams',
  Strain.CLUBS: 'clubs',
}


def _symbol(strain: Strain, quoting: Quoting) -> str:
  """A suit symbol as the tournament page marks one up."""
  return f'<span class={quoting}{_SYMBOL_CLASS[strain]} symbol{quoting}></span>'


def _tournament_level_cell(
  strain: Strain, values: tuple[int | None, ...], quoting: Quoting
) -> str:
  """A level cell, with the page's own spacing quirks."""
  if strain is Strain.NOTRUMP:
    return '/'.join(_dash(value) for value in values) + 'NT'
  if len(values) == 1:
    return f'{values[0]:>2}{_symbol(strain, quoting)}'
  first, second = values
  if second is None:
    # After a dash the page writes the strain's letter, not its symbol.
    return f'{_dash(first)}/-{_ACBL_STRAIN[strain]}'
  return f'{_dash(first)}/{second:>2}{_symbol(strain, quoting)}'


def _tournament_trick_cell(
  strain: Strain, values: tuple[int | None, ...], quoting: Quoting
) -> str:
  """A trick-count cell, wrapped as the page wraps one."""
  counts = '/'.join(_dash(value) for value in values)
  reverse = f'<div class={quoting}reverse{quoting}>'
  if strain is Strain.NOTRUMP:
    return f'{reverse}NT{counts}</div>'
  return f' {reverse}{_symbol(strain, quoting)}{counts}</div>'


def tournament_line(deal: Deal, side: Side, quoting: Quoting) -> str:
  """A side's `<span>NS: …</span>`.

  Unlike the club page, a side straddling seven tricks gets both cells: a level
  for the seat that makes something, and both seats' trick counts.
  """
  table = solve_table(deal)
  level_cells, trick_cells = [], []
  for strain in _STRAINS_LOW_TO_HIGH:
    tricks = tuple(table[seat][strain] for seat in side.seats)
    if any(count >= 7 for count in tricks):
      made = tuple(count - 6 if count >= 7 else None for count in tricks)
      level_cells.append(_tournament_level_cell(strain, _merged(made), quoting))
    if not all(count >= 7 for count in tricks):
      trick_cells.append(
        _tournament_trick_cell(strain, _merged(tricks), quoting)
      )
  cells = ''.join(' ' + cell for cell in level_cells + trick_cells)
  return f'<span>{side}:{cells}</span>'


def tournament_par(
  deal: Deal, board_number: int, quoting: Quoting
) -> str | None:
  """The par span, for the shapes real pages show; None for any other.

  An overtrick par is stated as the higher contract made exactly. A result after
  `NS` is wrapped as though the S were a spade contract — the page's renderer's
  mistake, mirrored here.
  """
  par = par_of(deal, board_number)
  if len(par.contracts) != 1:
    return None
  (contract,) = par.contracts
  if not contract.doublings and contract.result > 0:
    contract = dataclasses.replace(
      contract, level=contract.level + contract.result, result=0
    )
  declarer = _seats_name(contract.seats)
  result = f'{contract.result:+d}' if contract.result else ''
  score = f'{par.north_south_score:+d}'

  if contract.strain is Strain.NOTRUMP:
    if contract.doublings or result:
      return None
    return (
      f'<span>{score} {contract.level}'
      f'<div class={quoting}{quoting}>NT-</div>{declarer}</span>'
    )

  star = (
    f'<span style={quoting}font-size: 18px;display: inline;{quoting}>*</span>'
    * contract.doublings
  )
  bid = f'{contract.level:>2}{_symbol(contract.strain, quoting)}{star}'
  if declarer == 'NS' and result:
    spade = _symbol(Strain.SPADES, quoting)
    tail = f'-N <div class={quoting}{quoting}>{spade}{result}</div>'
  elif result and not contract.doublings:
    return None
  else:
    tail = f'-{declarer}{result}'
  return f'<span>{score} {bid}{tail}</span>'


# --- check: reproduce the real captures ---------------------------------------


@dataclasses.dataclass
class Tally:
  """How one format's check went."""

  checked: int = 0
  mismatched: int = 0
  # Par shapes the generator does not produce, so nothing was compared.
  skipped: int = 0

  def compare(self, where: str, published: str, generated: str) -> None:
    """Count one comparison, printing both texts if they differ.

    Only analysis text is ever printed — never a name or a result.
    """
    self.checked += 1
    if published == generated:
      return
    self.mismatched += 1
    if self.mismatched <= 5:
      print(f'--- {where}\n  published: {published}\n  generated: {generated}')


def _deals(traveller: Traveller) -> Mapping[int, Deal]:
  """A traveller's deals, by board number."""
  return {board.number: board.deal for board in traveller.boards if board.deal}


def _check_pbn(root: Path) -> Tally:
  """Compare every real PBN's three analysis tags with generated ones."""
  tally = Tally()
  row = r'(?:[NSEW] +\S+ +\S+.*\n)'
  patterns: Mapping[str, tuple[str, Callable[[Deal, int], str]]] = {
    'result table': (
      r'\[OptimumResultTable "[^"]*"\]\n' + row + '{20}',
      lambda deal, _: pbn_result_table(deal),
    ),
    'par': (
      r'\[OptimumScore "[^"]*"\]\n\[ParContract "[^"]*"\]',
      pbn_par_tags,
    ),
    'lead table': (
      r'\[OptimumOpeningLeadTable "[^"]*"\]\n' + row + '{20}',
      lambda deal, _: pbn_lead_table(deal),
    ),
  }
  for capture in sorted(root.rglob('*.pbn')):
    text = capture.read_text(encoding='latin-1')
    deals = _deals(
      club_pbn_parsing.parse_club_pbn(text, reference=_FIXTURE_REFERENCE)
    )
    for record in re.split(r'\n(?=\[Event )', text):
      number = re.search(r'\[Board "(\d+)"\]', record)
      deal = deals.get(int(number.group(1))) if number else None
      if not number or not deal:
        continue
      for name, (pattern, generate) in patterns.items():
        published = re.search(pattern, record)
        if published:
          tally.compare(
            f'{capture.name} board {number.group(1)} {name}',
            published.group(0).rstrip('\n'),
            generate(deal, int(number.group(1))),
          )
  return tally


# A recap's board container, running to the next one or the end of the page; and
# the analysis paragraph inside it, whose first line break is not its content.
_CLUB_BOARD = re.compile(r'<div id=Board(\d+)[ >].*?(?=<div id=Board|\Z)', re.S)
_CLUB_ANALYSIS = re.compile(r'<p class=bcdda[^>]*>\n?(.*?)</p>', re.S)


def _club_boards(text: str) -> list[tuple[int, re.Match[str]]]:
  """Each board's number and its analysis paragraph's match, in page order.

  An `R` recap's board containers carry a class and a `C` recap's do not.
  """
  boards = []
  for segment in _CLUB_BOARD.finditer(text):
    paragraph = _CLUB_ANALYSIS.search(text, segment.start(), segment.end())
    if paragraph:
      boards.append((int(segment.group(1)), paragraph))
  return boards


def _check_club(root: Path) -> Tally:
  """Compare every real recap's analysis paragraph with a generated one."""
  tally = Tally()
  for recap in sorted(root.rglob('*.htm')):
    text = recap.read_text()
    deals = _deals(
      club_html_parsing.parse_club_html(text, reference=_FIXTURE_REFERENCE)
    )
    for number, paragraph in _club_boards(text):
      deal = deals.get(number)
      if not deal:
        continue
      # A page fetched directly colors its suits inline; a fixture does not.
      published = re.sub(r' style="[^"]*"', '', paragraph.group(1)).strip()
      generated = club_paragraph(deal, number, ClubStyle.of(published))
      # Some publishers switch the lead notes off.
      if '<br><br>' not in published:
        generated = generated.split('<br><br>')[0]
      tally.compare(f'{recap.name} board {number}', published, generated)
  return tally


_ACBL_RECORD = re.compile(
  r'"board":\s*(\d+),\s*"(?:dealer|north_spades)"(.*?)'
  r'(?="board":\s*\d+,\s*"(?:dealer|north_spades)"|\Z)',
  re.S,
)
_ACBL_FIELD = re.compile(
  r'"(double_dummy_ns|double_dummy_ew|par)":\s*"([^"]*)"'
)


def _acbl_fields(deal: Deal, board_number: int) -> Mapping[str, str]:
  """A board's three analysis fields, as an ACBL club page holds them."""
  return {
    'double_dummy_ns': acbl_line(deal, Side.NORTH_SOUTH),
    'double_dummy_ew': acbl_line(deal, Side.EAST_WEST),
    'par': acbl_par(deal, board_number),
  }


def _check_acbl_club(root: Path) -> Tally:
  """Compare every real ACBL club page's analysis fields with generated ones."""
  tally = Tally()
  for page in sorted(root.rglob('*.html')):
    raw = page.read_text()
    deals = _deals(
      acbl_club_parsing.parse_acbl_club_html(raw, reference=_FIXTURE_REFERENCE)
    )
    text = html.unescape(raw).replace('\\/', '/')
    for record in _ACBL_RECORD.finditer(text):
      number = int(record.group(1))
      deal = deals.get(number)
      if not deal:
        continue
      published = dict(_ACBL_FIELD.findall(record.group(2)))
      for key, generated in _acbl_fields(deal, number).items():
        if key in published:
          tally.compare(
            f'{page.name} board {number} {key}', published[key], generated
          )
  return tally


_TOURNAMENT_PAR = re.compile(r'(Par Score</a> )(<span>.*?</span>)( </div>)')


def _check_tournament(root: Path) -> Tally:
  """Compare every real tournament page's analysis spans with generated ones.

  Boards pair with the page's analysis spans in page order.
  """
  tally = Tally()
  for page in sorted(root.rglob('*.html')):
    text = page.read_text()
    traveller = acbl_tournament_parsing.parse_acbl_tournament_html(
      text, reference=_FIXTURE_REFERENCE
    )
    boards = [board for board in traveller.boards if board.deal]
    lines = [line.strip() for line in text.splitlines()]
    north_south = [line for line in lines if line.startswith('<span>NS:')]
    east_west = [line for line in lines if line.startswith('<span>EW:')]
    pars = [
      match.group(2) for match in _TOURNAMENT_PAR.finditer(' '.join(lines))
    ]
    if not len(boards) == len(north_south) == len(east_west) == len(pars):
      print(f'{page.name}: boards and analysis spans do not pair up')
      continue
    for board, north_south_line, east_west_line, par in zip(
      boards, north_south, east_west, pars, strict=True
    ):
      assert board.deal
      where = f'{page.name} board {board.number}'
      for side, published in (
        (Side.NORTH_SOUTH, north_south_line),
        (Side.EAST_WEST, east_west_line),
      ):
        tally.compare(
          f'{where} {side}',
          published,
          tournament_line(board.deal, side, Quoting.SERVED),
        )
      generated_par = tournament_par(board.deal, board.number, Quoting.SERVED)
      if generated_par is None:
        tally.skipped += 1
      else:
        tally.compare(f'{where} par', par, generated_par)
  return tally


def check() -> int:
  """Run every format's check over the private tree's captures."""
  captures = discover_private_tree().traveller_captures
  checks: Sequence[tuple[str, Callable[[Path], Tally], Path]] = (
    ('club PBN', _check_pbn, captures / 'club'),
    ('club HTML', _check_club, captures / 'club'),
    ('ACBL club', _check_acbl_club, captures / 'acbl_club'),
    ('ACBL tournament', _check_tournament, captures / 'acbl_tournament'),
  )
  failed = False
  for name, run, root in checks:
    tally = run(root)
    print(
      f'{name}: {tally.checked} checked, {tally.mismatched} mismatched, '
      f'{tally.skipped} par shapes skipped'
    )
    failed = failed or tally.mismatched > 0
  return 1 if failed else 0


# --- rewrite: give the fixtures their deals' analysis -------------------------


class RewriteError(Exception):
  """A fixture lacks the analysis markup its rewrite expects."""


def _replace_once(pattern: str, replacement: str, text: str, what: str) -> str:
  """`text` with the one match of `pattern` replaced, verbatim."""
  replaced, count = re.subn(
    pattern, lambda _: replacement, text, count=1, flags=re.S
  )
  if count != 1:
    raise RewriteError(f'no {what} found')
  return replaced


def _rewrite_pbn(path: Path) -> None:
  """Give each board of a PBN fixture its deal's three analysis tags."""
  text = path.read_bytes().decode('latin-1')
  deals = _deals(
    club_pbn_parsing.parse_club_pbn(text, reference=_FIXTURE_REFERENCE)
  )
  row = r'(?:[NSEW] [^\n]*\n)'
  records = re.split(r'(\n(?=\[Event ))', text)
  for index, record in enumerate(records):
    number = re.search(r'\[Board "(\d+)"\]', record)
    deal = deals.get(int(number.group(1))) if number else None
    if not number or not deal:
      continue
    board = int(number.group(1))
    record = _replace_once(
      r'\[OptimumScore "[^"]*"\]\n\[ParContract "[^"]*"\]',
      pbn_par_tags(deal, board),
      record,
      f'par in board {board} of {path.name}',
    )
    record = _replace_once(
      r'\[OptimumOpeningLeadTable "[^"]*"\]\n' + row + '{20}',
      pbn_lead_table(deal) + '\n',
      record,
      f'lead table in board {board} of {path.name}',
    )
    records[index] = _replace_once(
      r'\[OptimumResultTable "[^"]*"\]\n' + row + '{20}',
      pbn_result_table(deal) + '\n',
      record,
      f'result table in board {board} of {path.name}',
    )
  path.write_bytes(''.join(records).encode('latin-1'))


def _rewrite_club_html(path: Path) -> None:
  """Give each board of a recap fixture its deal's analysis paragraph."""
  text = path.read_text()
  deals = _deals(
    club_html_parsing.parse_club_html(text, reference=_FIXTURE_REFERENCE)
  )
  # Replaced from the end, so earlier offsets stay valid.
  for number, paragraph in reversed(_club_boards(text)):
    generated = club_paragraph(
      deals[number], number, ClubStyle.of(paragraph.group(1))
    )
    text = text[: paragraph.start(1)] + generated + text[paragraph.end(1) :]
  path.write_text(text)


def _rewrite_acbl_club(path: Path) -> None:
  """Give each board of an ACBL club fixture its deal's analysis fields."""
  text = path.read_text()
  deals = _deals(
    acbl_club_parsing.parse_acbl_club_html(text, reference=_FIXTURE_REFERENCE)
  )
  for number, deal in deals.items():
    record = re.search(
      rf'"board":\s*{number},\s*"dealer".*?(?="board":\s*\d+,\s*"dealer"|\Z)',
      text,
      re.S,
    )
    if not record:
      raise RewriteError(f'no hand record for board {number} in {path.name}')
    body = record.group(0)
    for key, value in _acbl_fields(deal, number).items():
      fields = list(re.finditer(rf'"{key}":\s*"([^"]*)"', body))
      if len(fields) != 1:
        raise RewriteError(f'{key} for board {number} in {path.name}')
      body = body[: fields[0].start(1)] + value + body[fields[0].end(1) :]
    text = text[: record.start()] + body + text[record.end() :]
  path.write_text(text)


def _rewrite_tournament(path: Path) -> None:
  """Give each board of the tournament fixture its deal's analysis spans."""
  text = path.read_text()
  traveller = acbl_tournament_parsing.parse_acbl_tournament_html(
    text, reference=_FIXTURE_REFERENCE
  )
  boards = [board for board in traveller.boards if board.deal]
  cell = r'(?:[^<]|<span[^>]*></span>|<div[^>]*>|</div>)*'
  north_south = list(re.finditer(rf'<span>NS:{cell}</span>', text))
  east_west = list(re.finditer(rf'<span>EW:{cell}</span>', text))
  pars = list(_TOURNAMENT_PAR.finditer(text))
  if not len(boards) == len(north_south) == len(east_west) == len(pars):
    raise RewriteError(
      f'boards and analysis spans do not pair up in {path.name}'
    )

  replacements: list[tuple[int, int, str]] = []
  for board, north_south_match, east_west_match, par_match in zip(
    boards, north_south, east_west, pars, strict=True
  ):
    assert board.deal
    par = tournament_par(board.deal, board.number, Quoting.BROWSER_SAVED)
    if par is None:
      raise RewriteError(f'board {board.number} has a par shape not produced')
    replacements += [
      (
        north_south_match.start(),
        north_south_match.end(),
        tournament_line(board.deal, Side.NORTH_SOUTH, Quoting.BROWSER_SAVED),
      ),
      (
        east_west_match.start(),
        east_west_match.end(),
        tournament_line(board.deal, Side.EAST_WEST, Quoting.BROWSER_SAVED),
      ),
      (par_match.start(2), par_match.end(2), par),
    ]
  # Applied from the end, so earlier offsets stay valid.
  for start, end, value in sorted(replacements, reverse=True):
    text = text[:start] + value + text[end:]
  path.write_text(text)


_FIXTURE_REWRITES: Mapping[str, Callable[[Path], None]] = {
  'club_game.pbn': _rewrite_pbn,
  'club_game_r.htm': _rewrite_club_html,
  'club_game_c.htm': _rewrite_club_html,
  'acbl_club_game.html': _rewrite_acbl_club,
  'acbl_club_two_winner_movement.html': _rewrite_acbl_club,
  'acbl_tournament_session.html': _rewrite_tournament,
}


def rewrite(fixtures: Path) -> int:
  """Rewrite every fixture's analysis from its own deals, in place."""
  for name, rewrite_fixture in _FIXTURE_REWRITES.items():
    rewrite_fixture(fixtures / name)
    print(f'rewrote {name}')
  return 0


def main(argv: Sequence[str] | None = None) -> int:
  """Parse the subcommand and run it."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  subcommands = parser.add_subparsers(dest='subcommand', required=True)
  subcommands.add_parser(
    'check',
    help="regenerate every real capture's analysis and report where it differs",
  )
  rewrite_parser = subcommands.add_parser(
    'rewrite', help="rewrite each fixture's analysis from its own deals"
  )
  rewrite_parser.add_argument(
    '--fixtures',
    type=Path,
    default=_DEFAULT_FIXTURES,
    help='the directory holding the traveller fixtures',
  )
  args = parser.parse_args(argv)
  if args.subcommand == 'check':
    return check()
  return rewrite(args.fixtures)


if __name__ == '__main__':
  sys.exit(main())
