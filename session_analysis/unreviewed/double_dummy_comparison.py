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
landed exactly where best play does. Which side took the tricks is what the sign
absorbs. Where we declared, a gain is our taking more tricks than the double
dummy allows; where the opponents declared, it is their taking fewer. One
reading therefore holds for the whole column — positive is a board that went our
way — instead of flipping meaning with every board we defended.

There are two such comparisons — `BoardComparison` carries both — and the
difference between them is the point of having both:

- **Against the whole deal** (`whole_deal`). The deal's double-dummy table
  states the tricks available with best play on both sides, and best play by the
  defense includes its choice of lead — so this measures the whole board against
  everything the deal offered. The table is solved once, when its capture is
  stored, and reconciliation carries it onto the board, so here it is read
  rather than solved.
- **Against the deal after the lead actually made** (`after_lead`). No table can
  answer this one, so it is solved; `double_dummy_solving` is the seam.
  Measuring from the position the lead left rather than from the start of the
  deal takes the lead itself out of the reckoning, leaving what the play alone
  came to.

So the first is the whole board and the second is the play within it, and the
gap between them is what the opening lead was worth. Which way that gap can run
is fixed rather than free: the best lead is by definition the one holding
declarer to fewest tricks, so any other lead leaves declarer at least as many.
Declaring, `after_lead` never exceeds `whole_deal`, and the difference is what
the opponents' lead handed us; defending, it never falls below, and the
difference is what our own lead cost. A defense that found the killing lead
leaves nothing between them, so the two come back equal however the play then
went.

`session_summary` totals both over a whole session, split across our own seats
by `placement_of`.

Standing caveat on both: double-dummy play sees all four hands and nobody at the
table did, so a trick lost against a count has usually gone to a guess no one
could have avoided. The numbers measure what was there, not anyone's play.

A session no traveller has reached has neither table nor deal, and nothing here
has anything to say about it. The transcript reports that silence rather than
leaving it to read as a session whose every board came out even.
"""

import dataclasses
from collections.abc import Mapping, Sequence

from session_analysis import issue_reporting, traveller_store
from session_analysis.enums import Direction, IssueSeverity
from session_analysis.models import (
  Board,
  Contract,
  PlayedContract,
  Session,
)
from session_analysis.private_paths import PrivateTree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import deal_checks, double_dummy_solving

# A traveller that a session names but that cannot be read back. Worth reporting
# rather than passing over: the session says the capture was consulted, so a
# record either never stored or no longer parsing leaves the comparisons that
# capture would have supplied quietly missing.
_UNREADABLE_TRAVELLER = issue_reporting.Failure(
  'unreadable_traveller_record', IssueSeverity.LOW, 'traveller'
)


@dataclasses.dataclass(frozen=True)
class BoardComparison:
  """What the two comparisons made of one board, in tricks our side gained.

  Either count is None where that comparison could not be made, and the two fail
  independently: a board whose lead went unrecorded can still be set against its
  table, and one carrying a deal but no table can still be solved after its
  lead. A board neither reached is not represented at all.
  """

  whole_deal: int | None
  after_lead: int | None


@dataclasses.dataclass(frozen=True)
class Placement:
  """Which side of a board we were on, and the seat of ours it turned on."""

  declared_by_us: bool
  # The one that declared where we declared, the one that led where we defended.
  # Either way it is one of the two seats our pair sat in on that board, since
  # the lead comes from declarer's left — so a total split by it is always a
  # split across our own partnership.
  our_seat: Direction


def placement_of(board: Board) -> Placement | None:
  """Where the board puts us, or None where the record cannot say.

  A board passed out, or whose contract cell did not parse, names no declarer to
  place us against. Which side we sat is what reconciliation records, so a board
  it never placed us on is left unplaced rather than read from declarer's point
  of view — half of those would read backwards.
  """
  played = _played_contract(board)
  if not played or not board.our_pair:
    return None

  declarer = played.contract.declarer
  declared_by_us = declarer in board.our_pair.side.seats
  return Placement(
    declared_by_us=declared_by_us,
    # Defending, the seat of ours in play is the one on lead, which is the seat
    # to declarer's left.
    our_seat=declarer if declared_by_us else declarer.left_hand_opponent,
  )


def compare_boards(session: Session) -> Mapping[int, BoardComparison]:
  """Both comparisons for every board either of them could be made for.

  Keyed by board number. A board that `_comparable` turns away is absent, and so
  is one that neither comparison reached. The caller has nothing to print in
  either case, and the difference between the two reasons is not something a
  transcript's reader acts on.

  Both are gathered in one pass because they answer about the same board and are
  read side by side: the whole deal, and the play within it once the opening
  lead is taken out of the reckoning.
  """
  comparisons: dict[int, BoardComparison] = {}
  for board in session.boards:
    comparable = _comparable(board)
    if not comparable:
      continue

    table = board.solved_double_dummy_tricks
    whole_deal_tricks = (
      table[comparable.contract.declarer][comparable.contract.strain]
      if table
      else None
    )
    after_lead_tricks = _solved_tricks(board, comparable.contract)
    # Tested for stated values rather than truthy ones: a declarer holding no
    # trick at all is a count of zero.
    if whole_deal_tricks is None and after_lead_tricks is None:
      continue

    comparisons[comparable.number] = BoardComparison(
      whole_deal=(
        None
        if whole_deal_tricks is None
        else comparable.gain_on(whole_deal_tricks)
      ),
      after_lead=(
        None
        if after_lead_tricks is None
        else comparable.gain_on(after_lead_tricks)
      ),
    )
  return comparisons


def read_referenced_travellers(
  tree: PrivateTree, session: Session
) -> issue_reporting.Read[Sequence[Traveller]]:
  """Read back the stored travellers a session's provenance names.

  Reconciliation records which captures it consulted, so a session names its own
  travellers and nothing has to search the whole record root for them. That
  keeps the comparison honest as well as cheap: a capture of some other session
  that happens to number its boards the same way is never consulted here.

  A record that is missing or no longer parses costs only the comparisons it
  would have supplied, not the rest of the run, and is reported rather than
  passed over.
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

  Gathered once because both comparisons want the same things from a board —
  which board it was, what was played on it, and which side we were — and differ
  only in the count they set the result against.
  """

  number: int
  contract: Contract
  tricks_taken: int
  declared_by_us: bool

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
  # Which side we sat is what orients the sign, so an unplaced board has no
  # comparison to offer. A board is matched to its traveller row by the number
  # the sheet gave it, so one whose number could not be read carries nothing
  # from a traveller to compare against, and nothing to key its comparison by.
  placement = placement_of(board)
  if not board.number.schedule or not played or not placement:
    return None

  return _ComparableBoard(
    number=board.number.schedule.number,
    contract=played.contract,
    tricks_taken=played.result.tricks_taken,
    declared_by_us=placement.declared_by_us,
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
