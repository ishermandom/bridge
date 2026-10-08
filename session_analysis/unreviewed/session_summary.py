# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""How a session went, totalled by the role we played and the seat we sat.

A transcript's boards say what happened one at a time, and this module adds them
up into the groups a reader asks about: the boards we declared, the boards we
defended, each of those split by which of us was in play, and the session
itself. Every group carries the same measures side by side:

- **Matchpoints**, as a share of the most the group could have scored — the
  matchpoints its boards earned over the sum of their tops.
- **The two double-dummy counts**, `whole_deal` and `after_lead`, summed as
  `double_dummy_comparison` defines them.

The groups follow our own position rather than the table's, through
`double_dummy_comparison.placement_of`: a board we declared belongs to the seat
of ours that declared it, and a board we defended to the seat of ours that led.

The measures need different inputs, so they can cover different boards. A
percentage needs the board's matchpoints and top; of the double-dummy counts,
`whole_deal` needs the board's solved table and `after_lead` its deal and lead.
Each group therefore counts, beside its boards, how many of them each measure
covered, and a reader can be told when a total leaves some out.
"""

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from session_analysis.enums import Direction
from session_analysis.models import Board
from session_analysis.unreviewed import double_dummy_comparison


@dataclasses.dataclass(frozen=True)
class Totals:
  """What one group of boards came to, measure by measure.

  `boards` counts every board in the group. `scored` and `compared` count the
  ones each measure covered, which can be fewer: a board enters the matchpoints
  only with both its score and its top, and the double-dummy totals only with
  both counts. Totalling the two counts over different boards would leave them
  incomparable, and setting them side by side is what they are printed for.
  """

  boards: int = 0
  scored: int = 0
  matchpoints: Decimal = Decimal(0)
  tops: Decimal = Decimal(0)
  compared: int = 0
  whole_deal: int = 0
  after_lead: int = 0

  @property
  def percentage(self) -> Decimal | None:
    """The matchpoints earned, per hundred available; None if none scored."""
    if not self.scored:
      return None
    return 100 * self.matchpoints / self.tops

  @staticmethod
  def summed(groups: Iterable['Totals']) -> 'Totals':
    """Several groups of boards added into one."""
    gathered = list(groups)
    return Totals(
      boards=sum(totals.boards for totals in gathered),
      scored=sum(totals.scored for totals in gathered),
      matchpoints=sum(
        (totals.matchpoints for totals in gathered), start=Decimal(0)
      ),
      tops=sum((totals.tops for totals in gathered), start=Decimal(0)),
      compared=sum(totals.compared for totals in gathered),
      whole_deal=sum(totals.whole_deal for totals in gathered),
      after_lead=sum(totals.after_lead for totals in gathered),
    )


@dataclasses.dataclass(frozen=True)
class SessionSummary:
  """A session's totals: by role, by role and seat, and as a whole.

  A pair does not always keep one direction for a whole session, so a role can
  hold more than the two seats of a single partnership: a pair that changed
  direction mid-session may have declared from three seats over an evening, and
  each seat is its own group.

  Read across a group, the gap between the two double-dummy totals is what the
  opening leads were worth. Defending, `whole_deal` below `after_lead` is the
  cost of that seat's leads; declaring, `whole_deal` above `after_lead` is what
  the opponents' leads handed that declarer. Either way the difference runs the
  same way round as the totals do — our side's gain.
  """

  # Split by the seat of ours that declared, and that led, respectively. Seats
  # come in the order `Direction` declares them, so the groups read round the
  # table however the boards happened to fall.
  declaring: Mapping[Direction, Totals]
  defending: Mapping[Direction, Totals]
  # Every board, the unplaced ones included, so that the session's own score
  # stands here even where a board could not be put under any seat.
  whole_session: Totals
  # Boards with no seat of ours to put them under: passed out, a contract cell
  # that did not parse, or a board reconciliation never placed us on.
  unplaced: int
  # The distinct tops the boards were scored against, lowest first. A session
  # usually has one, but a board played fewer times than the rest has a lower
  # top of its own.
  tops: tuple[Decimal, ...]

  @property
  def declaring_total(self) -> Totals:
    """Every board we declared."""
    return Totals.summed(self.declaring.values())

  @property
  def defending_total(self) -> Totals:
    """Every board we defended."""
    return Totals.summed(self.defending.values())

  @property
  def seats(self) -> tuple[Direction, ...]:
    """Every seat of ours a board was put under, in the order they sit round."""
    return tuple(
      seat
      for seat in Direction
      if seat in self.declaring or seat in self.defending
    )


def summarize(
  boards: Sequence[Board],
  comparisons: Mapping[int, double_dummy_comparison.BoardComparison],
) -> SessionSummary:
  """Total the given boards into a session's groups.

  `comparisons` are the double-dummy counts `double_dummy_comparison` made of
  these boards, passed in rather than made here because solving is slow and the
  transcript already needs them for its board lines.
  """
  declaring: dict[Direction, list[Totals]] = {}
  defending: dict[Direction, list[Totals]] = {}
  every_board: list[Totals] = []
  unplaced = 0
  tops: set[Decimal] = set()

  for board in boards:
    top = board.matchpoint_top
    if top is not None:
      tops.add(_exact_matchpoints(top))
    schedule = board.number.schedule
    compared = comparisons.get(schedule.number) if schedule else None
    totals = _board_totals(
      matchpoints=board.matchpoints,
      top=top,
      comparison=compared,
    )
    every_board.append(totals)

    placement = double_dummy_comparison.placement_of(board)
    if not placement:
      unplaced += 1
      continue
    role = declaring if placement.declared_by_us else defending
    role.setdefault(placement.our_seat, []).append(totals)

  return SessionSummary(
    declaring=_by_seat(declaring),
    defending=_by_seat(defending),
    whole_session=Totals.summed(every_board),
    unplaced=unplaced,
    tops=tuple(sorted(tops)),
  )


def _board_totals(
  *,
  matchpoints: float | None,
  top: float | None,
  comparison: double_dummy_comparison.BoardComparison | None,
) -> Totals:
  """One board as a group of its own, carrying whichever measures it can."""
  totals = Totals(boards=1)
  # A bottom board scores zero, so absence is tested for rather than falsiness.
  if matchpoints is not None and top is not None:
    totals = dataclasses.replace(
      totals,
      scored=1,
      matchpoints=_exact_matchpoints(matchpoints),
      tops=_exact_matchpoints(top),
    )
  if (
    comparison
    and comparison.whole_deal is not None
    and comparison.after_lead is not None
  ):
    totals = dataclasses.replace(
      totals,
      compared=1,
      whole_deal=comparison.whole_deal,
      after_lead=comparison.after_lead,
    )
  return totals


def _by_seat(
  grouped: Mapping[Direction, Sequence[Totals]],
) -> Mapping[Direction, Totals]:
  """Each seat's boards totalled, the seats in the order they sit round."""
  return {
    seat: Totals.summed(grouped[seat]) for seat in Direction if seat in grouped
  }


def _exact_matchpoints(matchpoints: float) -> Decimal:
  """A score or top as an exact decimal, rather than a binary fraction.

  Sources print a score to at most two places, and reconciliation rounds a top
  to two places as well, so the float's shortest spelling is the two-place value
  it stands for. Summing scores and tops as decimals keeps a total such as `4.17
  + 2.33` from drifting off the hundredth it should land on.
  """
  return Decimal(str(matchpoints))
