# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""How a board's result compares with what the deal itself allowed.

A result read on its own says only what happened. Set beside the double-dummy
analysis of the same deal, it says something more useful: whether the play at
the table found what was there. This module makes that comparison board by
board, for the transcript to print.

Each comparison is a signed count of tricks, read from our own side's point of
view rather than from declarer's: `+1` says the board went a trick our way
against what best play yields, `-2` two tricks against us, and `0` that it
landed exactly where best play does. Which table the tricks were won at is what
the sign absorbs. Where we declared, a gain is our taking more tricks than the
double dummy allows; where the opponents declared, it is their taking fewer. One
reading therefore holds down the whole column — positive is a board that went
our way — instead of flipping meaning with every board we defended.

There are two such comparisons — `BoardComparison` carries both — and the
difference between them is the point of having both:

- **Against the published table** (`whole_deal`). The table states the tricks
  available with best play on both sides, and best play by the defense includes
  its choice of lead — so this measures the whole board against everything the
  deal offered. It is read from a traveller rather than solved.
- **Against the deal after the lead actually made** (`after_lead`). No table can
  answer this one, so it is solved; `double_dummy_solving` is the seam.
  Measuring from the position the lead left rather than from the start of the
  deal takes the lead itself out of the reckoning, leaving what the play alone
  came to.

So the first is the whole board and the second is the play within it, and the
gap between them is what the opening lead was worth. Which way that gap can run
is fixed rather than free: the best lead is by definition the one holding
declarer to fewest tricks, so any other lead leaves declarer at least as many,
and `after_lead` can only move away from `whole_deal` in the direction the
leading side owns. Declaring, `after_lead` never exceeds `whole_deal`, and the
difference is what the opponents' lead handed us; defending, it never falls
below, and the difference is what our own lead cost. A defense that found the
killing lead leaves nothing between them, so the two come back equal however
the play then went.

`SessionRecap` totals both over a whole session, split across our own seats.

Standing caveat on both: double-dummy play sees all four hands and nobody at the
table did, so a trick lost against a count has usually gone to a guess no one
could have avoided. The numbers measure what was there, not anyone's play.

Only a pairs game publishes a traveller, so a teams session has neither table
nor deal and nothing here has anything to say about it. The transcript reports
that silence rather than leaving it to read as a board that came out even.
"""

import dataclasses
from collections.abc import Iterable, Mapping, Sequence

from session_analysis import issue_reporting, traveller_store
from session_analysis.enums import Direction, IssueSeverity, Strain
from session_analysis.models import (
  Board,
  Contract,
  PlayedContract,
  Session,
)
from session_analysis.private_paths import PrivateTree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import deal_checks, double_dummy_solving

# A traveller a session names but nothing can read back. Worth reporting rather
# than passing over: the session says the capture was consulted, so its absence
# means the record was never stored or no longer parses, and either way the
# comparisons that capture would have supplied are quietly missing.
_UNREADABLE_TRAVELLER = issue_reporting.Failure(
  'unreadable_traveller_record', IssueSeverity.LOW, 'traveller'
)


@dataclasses.dataclass(frozen=True)
class BoardComparison:
  """What the two comparisons made of one board, in tricks our side gained.

  Either count is None where that comparison could not be made, and the two
  fail independently: a source listing only its makeable contracts states no
  cell for a declarer held under seven tricks and yet gives the deal, so
  `after_lead` can answer where `whole_deal` cannot. A board neither reached is
  not represented at all.
  """

  declared_by_us: bool
  # The seat of ours the board turned on: the one that declared where we
  # declared, the one that led where we defended. Either way it is one of our
  # own two, since the lead comes from declarer's left — so a recap split by it
  # is always a split across our own partnership.
  our_seat: Direction
  whole_deal: int | None
  after_lead: int | None


def compare_boards(
  session: Session, travellers: Sequence[Traveller]
) -> Mapping[int, BoardComparison]:
  """Both comparisons for every board either of them could be made for.

  Keyed by board number. A board `_comparable` turns away is absent, as is one
  neither comparison reached — the caller has nothing to print for either, and
  the reasons differ in ways no reader of a transcript acts on.

  Both are gathered in one pass because they answer about the same board and
  are read side by side: the whole deal, and the play within it once the
  opening lead is taken out of the reckoning.
  """
  comparisons: dict[int, BoardComparison] = {}
  for board in session.boards:
    comparable = _comparable(board)
    if not comparable:
      continue

    published = _published_tricks(
      travellers,
      board_number=comparable.number,
      declarer=comparable.contract.declarer,
      strain=comparable.contract.strain,
    )
    solved = _solved_tricks(board, comparable.contract)
    # Tested for stated values rather than truthy ones: a declarer holding no
    # trick at all is a count of zero, which a source does state.
    if published is None and solved is None:
      continue

    comparisons[comparable.number] = BoardComparison(
      declared_by_us=comparable.declared_by_us,
      our_seat=comparable.our_seat,
      whole_deal=None if published is None else comparable.gain_on(published),
      after_lead=None if solved is None else comparable.gain_on(solved),
    )
  return comparisons


@dataclasses.dataclass(frozen=True)
class ComparisonTotals:
  """What the two comparisons came to over one group of boards."""

  boards: int
  whole_deal: int
  after_lead: int

  @staticmethod
  def summed(totals: Iterable['ComparisonTotals']) -> 'ComparisonTotals':
    """Several groups of boards added into one."""
    gathered = list(totals)
    return ComparisonTotals(
      boards=sum(one.boards for one in gathered),
      whole_deal=sum(one.whole_deal for one in gathered),
      after_lead=sum(one.after_lead for one in gathered),
    )


@dataclasses.dataclass(frozen=True)
class RecapHalf:
  """The boards we played in one role, split across the seats we sat in it.

  A pair does not always keep one direction for a whole session, so `by_seat`
  can hold more than the two seats of a single partnership — a pair that moved
  declared from three seats over an evening, and each is its own row.
  """

  by_seat: Mapping[Direction, ComparisonTotals]

  @property
  def total(self) -> ComparisonTotals:
    """Every seat in this half together."""
    return ComparisonTotals.summed(self.by_seat.values())


@dataclasses.dataclass(frozen=True)
class SessionRecap:
  """The session's comparisons totalled, always split across our own seats.

  Both halves are organized by our position rather than by the table's. Where
  we declared, the boards are grouped by which of us declared; where we
  defended, by which of us led. The opponents' seats never appear, and they do
  not need to: the lead comes from declarer's left, so a board they declared is
  one we led, and every board therefore lands under one of our own two seats.

  Read across a row, the gap between the two totals is what the opening leads
  were worth. Defending, `whole_deal` short of `after_lead` is the cost of that
  seat's leads; declaring, `whole_deal` beyond `after_lead` is what the
  opponents' leads handed that declarer. Either way the difference runs the
  same way round as the totals do — our side's gain.
  """

  # Split by the seat of ours that declared, and that led, respectively.
  declaring: RecapHalf
  defending: RecapHalf
  # Boards carrying one count but not the other, and so left out of every row:
  # totalling two columns over different boards would leave them incomparable,
  # which is the one thing a row of this table is read for.
  partly_compared: int

  @property
  def whole_session(self) -> ComparisonTotals:
    """Both halves together — all the boards the recap could count."""
    return ComparisonTotals.summed([self.declaring.total, self.defending.total])


def recap_of(comparisons: Mapping[int, BoardComparison]) -> SessionRecap:
  """Total a session's comparisons into the rows a recap prints.

  Each row's seats come out in the order `Direction` declares them, so a recap
  reads round the table however the boards happened to fall.
  """
  declaring: dict[Direction, list[tuple[int, int]]] = {}
  defending: dict[Direction, list[tuple[int, int]]] = {}
  partly_compared = 0

  for comparison in comparisons.values():
    whole_deal, after_lead = comparison.whole_deal, comparison.after_lead
    if whole_deal is None or after_lead is None:
      partly_compared += 1
      continue
    group = declaring if comparison.declared_by_us else defending
    group.setdefault(comparison.our_seat, []).append((whole_deal, after_lead))

  return SessionRecap(
    declaring=_by_seat(declaring),
    defending=_by_seat(defending),
    partly_compared=partly_compared,
  )


def _by_seat(
  grouped: Mapping[Direction, Sequence[tuple[int, int]]],
) -> RecapHalf:
  """Each seat's boards totalled, the seats in the order they sit round."""
  return RecapHalf(
    {seat: _totals(grouped[seat]) for seat in Direction if seat in grouped}
  )


def _totals(counts: Sequence[tuple[int, int]]) -> ComparisonTotals:
  """One group of boards totalled, each board a pair of the two counts."""
  return ComparisonTotals(
    boards=len(counts),
    whole_deal=sum(whole_deal for whole_deal, _ in counts),
    after_lead=sum(after_lead for _, after_lead in counts),
  )


def read_referenced_travellers(
  tree: PrivateTree, session: Session
) -> issue_reporting.Read[Sequence[Traveller]]:
  """Read back the stored travellers a session's provenance names.

  Reconciliation records which captures it consulted, so a session names its own
  travellers and nothing has to search the whole record root for them. That
  keeps the comparison honest as well as cheap: a capture of some other session
  that happens to number its boards the same way is never consulted here.

  A record that is missing or no longer parses costs its own contribution and
  not the run's, and is reported rather than passed over.
  """
  travellers = []
  issues = []
  for reference in session.source.travellers:
    record = traveller_store.record_for(tree, reference.path)
    try:
      text = record.read_text()
    except OSError as error:
      issues.append(
        _UNREADABLE_TRAVELLER.issue(f'could not read {record}: {error}')
      )
      continue

    try:
      travellers.append(Traveller.model_validate_json(text))
    except ValueError as error:
      issues.append(
        _UNREADABLE_TRAVELLER.issue(
          f'{record} holds no traveller record: {error}'
        )
      )
  return issue_reporting.Read(tuple(travellers), tuple(issues))


@dataclasses.dataclass(frozen=True)
class _ComparableBoard:
  """What every comparison needs from a board, before its own inputs.

  Gathered once because both comparisons want the same three things — which
  board, what was played, and whether the declarer was us — and differ only in
  the count they set the result against.
  """

  number: int
  contract: Contract
  tricks_taken: int
  declared_by_us: bool
  # The seat of ours the board turned on; `BoardComparison.our_seat` says why
  # one seat of ours always answers, whichever side declared.
  our_seat: Direction

  def gain_on(self, available: int) -> int:
    """The tricks our side gained on a count, from our own point of view.

    Tricks beyond the count are declarer's, so they are ours only when we
    declared; defending, that same surplus is what the opponents took off us.
    """
    beyond_the_count = self.tricks_taken - available
    return beyond_the_count if self.declared_by_us else -beyond_the_count


def _comparable(board: Board) -> _ComparableBoard | None:
  """The board's half of a comparison, or None where it has none to offer.

  A row left blank, a contract cell that did not parse, and a board passed out
  all yield None: none of the three names a contract, and it is a contract — its
  strain and its declarer — that has a double-dummy count to compare with.
  """
  played = _played_contract(board)
  # A board is found by the number the sheet gave it, so one whose number could
  # not be read reaches no traveller row. Which side we sat is what orients the
  # sign, and reconciliation is what fills it, so a board it never placed us on
  # is left uncompared rather than compared from declarer's point of view — half
  # of those would read backwards.
  if not board.number.schedule or not played or not board.our_pair:
    return None

  declarer = played.contract.declarer
  declared_by_us = declarer in board.our_pair.side.seats
  return _ComparableBoard(
    number=board.number.schedule.number,
    contract=played.contract,
    tricks_taken=played.result.tricks_taken,
    declared_by_us=declared_by_us,
    # Defending, the seat of ours in play is the one on lead, which is the seat
    # to declarer's left.
    our_seat=declarer if declared_by_us else declarer.left_hand_opponent,
  )


def _played_contract(board: Board) -> PlayedContract | None:
  """The contract the board was played in, if the sheet recorded one."""
  resolution = board.outcome.resolution if board.outcome else None
  return resolution if isinstance(resolution, PlayedContract) else None


def _solved_tricks(board: Board, contract: Contract) -> int | None:
  """The tricks the deal yields after the lead this board actually recorded.

  None wherever the position cannot be stated: a board carrying no deal, one
  whose lead went unrecorded or unread, and one whose deal or lead the checks in
  `deal_checks` object to. The last is the interesting silence — a lead that is
  not in the leading hand means the sheet's lead, its declarer or its board
  number is wrong — and it is reported there rather than here, being a finding
  about the record rather than about this report.
  """
  lead = board.opening_lead.card if board.opening_lead else None
  if not board.deal or not lead:
    return None

  # The solver's two preconditions, in the one place that already states them.
  # Checked rather than caught: a malformed deal reaching the solver comes back
  # as an error naming nothing a reviewer could act on.
  if deal_checks.find_deal_issues(board.deal):
    return None
  if deal_checks.find_lead_issues(
    board.deal, declarer=contract.declarer, opening_lead=lead
  ):
    return None

  return double_dummy_solving.tricks_after_lead(
    board.deal,
    declarer=contract.declarer,
    strain=contract.strain,
    opening_lead=lead,
  )


def _published_tricks(
  travellers: Sequence[Traveller],
  *,
  board_number: int,
  declarer: Direction,
  strain: Strain,
) -> int | None:
  """The tricks the published tables give that declarer in that strain.

  None where no source states the cell, which is an ordinary answer rather than
  a failure: the club's HTML lists the makeable contracts alone, so it says
  nothing at all about a declarer held under seven tricks.

  None again where two sources state the cell and disagree. Nothing picks a
  winner, for the reason reconciliation's own merge does not either — a silent
  tiebreak between two records hides exactly the disagreement worth seeing.
  """
  stated: set[int] = set()
  for traveller in travellers:
    tricks = _stated_cell(
      traveller, board_number=board_number, declarer=declarer, strain=strain
    )
    if tricks is not None:
      stated.add(tricks)

  return stated.pop() if len(stated) == 1 else None


def _stated_cell(
  traveller: Traveller,
  *,
  board_number: int,
  declarer: Direction,
  strain: Strain,
) -> int | None:
  """What one traveller's table says for one declarer and strain.

  None both for a board this traveller does not record and for one it records
  without an analysis — a source that publishes results without hands states no
  table at all.
  """
  for board in traveller.boards:
    if board.number == board_number:
      if not board.double_dummy_tricks:
        return None
      # Indexed rather than looked up defensively: a table holds all twenty
      # cells by construction, and states a cell it has nothing to say about as
      # None. See `travellers.DoubleDummyTricks`.
      return board.double_dummy_tricks[declarer][strain]
  return None
