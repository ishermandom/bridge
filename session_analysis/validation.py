# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The non-raising validation pass over a built board.

A pure pass that returns `Issue`s rather than raising: a failure never aborts
the pipeline, it ranks the board higher in the review queue (nothing is
garbage). The checks operate on a fully built `Board` regardless of how it was
constructed — the parser or a human edit in the review UI — so they re-check
content the parser's regexes mostly guarantee but the model's types do not.

The checks, by concern (see models.md, Validation):

- Content well-formedness — each call, the lead, and the contract resolved to a
  canonical value; contract level in 1-7; tricks_taken in 0-13. Card legality
  ("the lead is a real card") collapses into lead resolvability: a `Card` is
  built from enum-typed rank and suit, so any resolved lead is already a real
  card, with no separate check to make.
- Transcription completeness — a played board should carry an opening lead and a
  transcribed auction; both are legitimately absent only on a passout, so on a
  played board their absence is a review prompt (a forgotten lead is often
  recoverable from memory if flagged early).
- Auction legality — bid rank strictly increases across successive bids; a
  double follows a bid and a redouble follows a double, each made by the correct
  side; the last bid equals the stated contract, with a consistent penalty. The
  auction and contract cells are transcribed independently, so these are
  cross-checks between two transcriptions.

Two judgments the pass deliberately leaves alone:

- The declarer is not derived from the auction. Passes are usually not written
  down, so the seat rotation can't be reconstructed and even the opening side is
  ambiguous; the contract cell's stated declarer is taken as given here and
  cross-checked against the travellers at reconciliation (where neither source
  is assumed correct).
- Whether a `+N` make reaches its contract is not judged here. The sheet's
  `+`/`-` sign is still in the cell's raw text (`Outcome.raw`), but is already
  gone from the typed `Result.tricks_taken` this pass reads; re-deriving it here
  would mean re-parsing text the parser already parsed. The check lives in the
  parser instead (see parsing.py), right where the sign is already in hand
  mid-parse.

Because passes are usually omitted, every legality check leans only on the
recorded bid order and each call's `by_opponents` flag (the circle convention),
never on an absolute seat.
"""

from collections.abc import Iterator, Sequence
from itertools import pairwise

from session_analysis.enums import CallKind, IssueSeverity, Penalty, Strain
from session_analysis.models import (
  AuctionEntry,
  Board,
  Call,
  Issue,
  Passout,
  PlayedContract,
  Session,
)

# Issue codes, one per check. String-valued to match the codes the parser
# already emits (see parsing.py); a shared enum spanning both modules is a
# possible future consolidation.
_UNRESOLVED_CALL = 'unresolved_call'
_UNRESOLVED_LEAD = 'unresolved_lead'
_UNRESOLVED_CONTRACT = 'unresolved_contract'
_CONTRACT_LEVEL_OUT_OF_RANGE = 'contract_level_out_of_range'
_TRICKS_OUT_OF_RANGE = 'tricks_out_of_range'
_LEAD_MISSING = 'lead_missing'
_AUCTION_MISSING = 'auction_missing'
_AUCTION_RANK_NOT_INCREASING = 'auction_rank_not_increasing'
_DOUBLE_WITHOUT_BID = 'double_without_bid'
_DOUBLE_BY_WRONG_SIDE = 'double_by_wrong_side'
_REDOUBLE_WITHOUT_DOUBLE = 'redouble_without_double'
_REDOUBLE_BY_WRONG_SIDE = 'redouble_by_wrong_side'
_CONTRACT_NOT_LAST_BID = 'contract_not_last_bid'
_CONTRACT_PENALTY_MISMATCH = 'contract_penalty_mismatch'
_PASSOUT_HAS_BIDS = 'passout_has_bids'
_CONTRACT_WITHOUT_BID = 'contract_without_bid'

# The rank order of strains in an auction: clubs lowest, notrump highest. A bid
# outranks another by level first, then by this order at equal level.
_STRAIN_RANK = {
  Strain.CLUBS: 0,
  Strain.DIAMONDS: 1,
  Strain.HEARTS: 2,
  Strain.SPADES: 3,
  Strain.NOTRUMP: 4,
}

_CONTRACT_LEVELS = range(1, 7 + 1)
_POSSIBLE_TRICKS = range(0, 13 + 1)

# One auction token whose call resolved: the envelope (for its `by_opponents`
# side flag) paired with its parsed `Call`.
_ResolvedCall = tuple[AuctionEntry, Call]


def find_issues(board: Board) -> Sequence[Issue]:
  """Return every validation issue found on a built board, never raising.

  Composes the content, completeness, and auction-legality checks. An empty
  result means the board passed; the issues are board-level, each carrying a
  `location` that points at the offending cell or auction token.
  """
  issues: list[Issue] = []
  issues.extend(_check_content(board))
  issues.extend(_check_completeness(board))
  issues.extend(_check_auction_legality(board))
  return tuple(issues)


def validate_board(board: Board) -> Board:
  """Return a copy of the board with its validation issues merged in.

  The models are frozen, so this builds a new `Board` rather than mutating;
  found issues are appended to any the parser already attached.
  """
  return board.model_copy(
    update={'issues': (*board.issues, *find_issues(board))}
  )


def validate_session(session: Session) -> Session:
  """Return a copy of the session with every board validated.

  Validation is board-scoped, so this maps `validate_board` over the boards and
  leaves the session-level fields (date, provenance) untouched.
  """
  validated_boards = tuple(validate_board(board) for board in session.boards)
  return session.model_copy(update={'boards': validated_boards})


def _check_content(board: Board) -> Iterator[Issue]:
  """Yield issues for unresolved tokens and out-of-range contract values."""
  for index, entry in enumerate(board.auction):
    # A null call is a token the parser couldn't understand; surface it at the
    # board level too, so it counts toward the board's review priority.
    if not entry.call:
      yield Issue(
        code=_UNRESOLVED_CALL,
        severity=IssueSeverity.MEDIUM,
        message=f'auction token did not resolve to a call: {entry.raw!r}',
        location=f'auction[{index}]',
      )

  # A present lead that failed to resolve is a problem; a missing lead is the
  # completeness check's concern, not this one.
  if board.opening_lead and not board.opening_lead.card:
    yield Issue(
      code=_UNRESOLVED_LEAD,
      severity=IssueSeverity.MEDIUM,
      message=f'opening lead did not resolve to a card: '
      f'{board.opening_lead.raw!r}',
      location='opening_lead',
    )

  if board.outcome and not board.outcome.resolution:
    yield Issue(
      code=_UNRESOLVED_CONTRACT,
      severity=IssueSeverity.MEDIUM,
      message=f'contract cell did not resolve: {board.outcome.raw!r}',
      location='outcome',
    )

  # Range checks apply only to a fully resolved played contract.
  if board.outcome and isinstance(board.outcome.resolution, PlayedContract):
    played = board.outcome.resolution
    if played.contract.level not in _CONTRACT_LEVELS:
      yield Issue(
        code=_CONTRACT_LEVEL_OUT_OF_RANGE,
        severity=IssueSeverity.HIGH,
        message=f'contract level {played.contract.level} is not in 1-7',
        location='outcome',
      )
    if played.result.tricks_taken not in _POSSIBLE_TRICKS:
      yield Issue(
        code=_TRICKS_OUT_OF_RANGE,
        severity=IssueSeverity.HIGH,
        message=f'tricks taken {played.result.tricks_taken} is not in 0-13',
        location='outcome',
      )


def _check_completeness(board: Board) -> Iterator[Issue]:
  """Yield review prompts for a played board missing its lead or auction.

  A lead and an auction are expected on any board that was actually played; both
  are legitimately absent only on a passout. When the contract cell didn't
  resolve we can't tell which case it is, so the unresolved-contract issue
  stands alone and this check keeps quiet.
  """
  if not board.outcome or not isinstance(
    board.outcome.resolution, PlayedContract
  ):
    return

  if not board.opening_lead:
    yield Issue(
      code=_LEAD_MISSING,
      severity=IssueSeverity.MEDIUM,
      message='no opening lead recorded for a played board',
      location='opening_lead',
    )

  if not board.auction:
    yield Issue(
      code=_AUCTION_MISSING,
      severity=IssueSeverity.MEDIUM,
      message='no auction transcribed for a played board',
      location='auction',
    )


def _check_auction_legality(board: Board) -> Iterator[Issue]:
  """Yield issues for an illegal or contract-inconsistent auction.

  Runs only on a transcribed auction whose every token resolved: a hole would
  make the bid sequence untrustworthy, so the pass stays silent and lets the
  content check own the unresolved token.
  """
  entries = board.auction
  if not entries:
    return

  # Pair each entry with its resolved call; a shorter list means the auction had
  # a hole, so we bail. The `if entry.call` filter also narrows the call type
  # from `Call | None` to `Call` for the checks below.
  resolved: list[_ResolvedCall] = [
    (entry, entry.call) for entry in entries if entry.call
  ]
  if len(resolved) != len(entries):
    return

  yield from _check_rank_monotonicity(resolved)
  yield from _check_double_redouble_legality(resolved)

  # The remaining checks cross the auction against the contract cell, so they
  # need a resolved outcome to compare against.
  if not board.outcome or not board.outcome.resolution:
    return
  resolution = board.outcome.resolution

  if isinstance(resolution, Passout):
    # A passed-out board has no bids; any bid contradicts the contract cell.
    if any(call.kind == CallKind.BID for _, call in resolved):
      yield Issue(
        code=_PASSOUT_HAS_BIDS,
        severity=IssueSeverity.HIGH,
        message='contract cell reads passout but the auction contains bids',
        location='auction',
      )
    return

  yield from _check_contract_matches_auction(resolved, resolution)


def _check_rank_monotonicity(
  resolved: Sequence[_ResolvedCall],
) -> Iterator[Issue]:
  """Yield an issue where a bid fails to outrank the bid before it.

  Only bids advance the rank; passes, doubles, and redoubles sit between them
  without changing it. Each bid must strictly exceed its predecessor.
  """
  bids = _bids(resolved)
  for (_, previous), (index, current) in pairwise(bids):
    if _bid_rank(current) <= _bid_rank(previous):
      yield Issue(
        code=_AUCTION_RANK_NOT_INCREASING,
        severity=IssueSeverity.HIGH,
        message='bid does not outrank the preceding bid',
        location=f'auction[{index}]',
      )


def _check_double_redouble_legality(
  resolved: Sequence[_ResolvedCall],
) -> Iterator[Issue]:
  """Yield issues for a double or redouble that breaks the auction's rules.

  A double must follow a bid — the contract it doubles — and be made by the
  opposing side; a redouble must follow a double and be made by the doubled
  side. 'Follows' means the nearest preceding non-pass call, since passes
  between calls are usually not written down. The side test reads each call's
  `by_opponents` flag rather than a seat, which omitted passes make unknowable.
  """
  for index, (entry, call) in enumerate(resolved):
    if call.kind not in (CallKind.DOUBLE, CallKind.REDOUBLE):
      continue
    preceding = _preceding_non_pass(resolved, index)
    location = f'auction[{index}]'

    if call.kind == CallKind.DOUBLE:
      if preceding is None or preceding[1].kind != CallKind.BID:
        yield Issue(
          code=_DOUBLE_WITHOUT_BID,
          severity=IssueSeverity.HIGH,
          message='double does not follow a bid',
          location=location,
        )
      elif entry.by_opponents == preceding[0].by_opponents:
        yield Issue(
          code=_DOUBLE_BY_WRONG_SIDE,
          severity=IssueSeverity.MEDIUM,
          message='double is by the same side as the bid it doubles',
          location=location,
        )
    else:  # A redouble.
      if preceding is None or preceding[1].kind != CallKind.DOUBLE:
        yield Issue(
          code=_REDOUBLE_WITHOUT_DOUBLE,
          severity=IssueSeverity.HIGH,
          message='redouble does not follow a double',
          location=location,
        )
      elif entry.by_opponents == preceding[0].by_opponents:
        yield Issue(
          code=_REDOUBLE_BY_WRONG_SIDE,
          severity=IssueSeverity.MEDIUM,
          message='redouble is by the same side as the double it answers',
          location=location,
        )


def _check_contract_matches_auction(
  resolved: Sequence[_ResolvedCall], resolution: PlayedContract
) -> Iterator[Issue]:
  """Yield issues where the contract cell disagrees with the auction.

  Cross-checks the played contract against the auction's endpoints: the last
  bid's strain and level, and the trailing double state (its penalty).
  """
  contract = resolution.contract
  bids = _bids(resolved)

  if not bids:
    yield Issue(
      code=_CONTRACT_WITHOUT_BID,
      severity=IssueSeverity.HIGH,
      message='contract cell names a contract but the auction has no bid',
      location='auction',
    )
    return

  last_index, last_bid = bids[-1]
  # A bid always carries a level and strain (see Call); assert it for the type
  # checker, since `_bids` already selected only bids.
  assert last_bid.level is not None and last_bid.strain is not None
  if (last_bid.level, last_bid.strain) != (contract.level, contract.strain):
    yield Issue(
      code=_CONTRACT_NOT_LAST_BID,
      severity=IssueSeverity.HIGH,
      message=f'contract {contract.level}{contract.strain.value} does not '
      f'match the last bid {last_bid.level}{last_bid.strain.value}',
      location='outcome',
    )

  # The penalty is whatever double or redouble trails the final bid.
  trailing_calls = [call for _, call in resolved[last_index + 1 :]]
  trailing_penalty = _trailing_penalty(trailing_calls)
  if trailing_penalty != contract.penalty:
    yield Issue(
      code=_CONTRACT_PENALTY_MISMATCH,
      severity=IssueSeverity.HIGH,
      message=f'contract penalty {contract.penalty.value} does not match the '
      f'auction, which ends {trailing_penalty.value}',
      location='outcome',
    )


def _bids(resolved: Sequence[_ResolvedCall]) -> Sequence[tuple[int, Call]]:
  """Return each bid paired with its index in the resolved auction."""
  return [
    (index, call)
    for index, (_, call) in enumerate(resolved)
    if call.kind == CallKind.BID
  ]


def _preceding_non_pass(
  resolved: Sequence[_ResolvedCall], index: int
) -> _ResolvedCall | None:
  """Return the nearest resolved call before `index` that is not a pass."""
  for candidate in reversed(resolved[:index]):
    if candidate[1].kind != CallKind.PASS:
      return candidate
  return None


def _bid_rank(call: Call) -> tuple[int, int]:
  """Return a bid's sort key: level first, then strain order.

  Assumes a bid call, so level and strain are both present; the auction-legality
  pass only reaches this with resolved bids.
  """
  assert call.level is not None and call.strain is not None
  return (call.level, _STRAIN_RANK[call.strain])


def _trailing_penalty(trailing_calls: Sequence[Call]) -> Penalty:
  """Return the penalty implied by the calls after the final bid.

  Takes the whole tail rather than the last call because the auction can end in
  passes after the double or redouble (`4S X p p p`), so the final token might
  be a pass; in which case, the double or redouble that sets the penalty sits
  earlier.
  """
  kinds = {call.kind for call in trailing_calls}
  if CallKind.REDOUBLE in kinds:
    return Penalty.REDOUBLED
  if CallKind.DOUBLE in kinds:
    return Penalty.DOUBLED
  return Penalty.NONE
