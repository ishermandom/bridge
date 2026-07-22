# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Vote between two independent transcriptions of the same sheet.

Two vision model runs over the same strips read markup independently; where they
agree, the agreement is itself evidence the transcription is likely to be right,
and where they disagree, that disagreement pinpoints exactly the cells worth a
human look.

`vote_sessions` is the entry point: it compares two already-parsed and
-validated `Session`s cell by cell and merges them into one, carrying through
whichever cells agree and flagging the ones that don't with a
`voting_disagreement` issue naming both candidates. The comparison is over each
cell's *parsed* value, never its raw transcription: two runs legitimately vary
between equivalent notations (`x` vs `X` for a double, `(*)` vs `(x)` for a
circled double), which the parser already normalizes, so comparing raw text
would flag those agreements as false disagreements.
"""

import itertools

from session_analysis.enums import IssueSeverity
from session_analysis.models import (
  AuctionEntry,
  Board,
  Call,
  Issue,
  Lead,
  Outcome,
  Session,
)

_VOTING_DISAGREEMENT = 'voting_disagreement'
_VOTING_BOARD_COUNT_MISMATCH = 'voting_board_count_mismatch'
_VOTING_UNCORROBORATED_BOARD = 'voting_uncorroborated_board'


def _voting_issue(location: str, candidate_a: str, candidate_b: str) -> Issue:
  """One issue flagging a cell the two runs disagreed on.

  Carries both raw candidates so a reviewer can resolve the disagreement against
  the image crop without rerunning anything.
  """
  return Issue(
    code=_VOTING_DISAGREEMENT,
    severity=IssueSeverity.HIGH,
    message=(
      f'the two vision model extraction runs disagreed on {location}: '
      f'{candidate_a!r} vs {candidate_b!r}'
    ),
    location=location,
  )


def _call_signature(call: Call | None) -> object:
  """What voting compares for a call: its meaning, not an announcement's raw
  transcription text.

  `Call` has no raw field of its own, but a bid's `announcement` carries one —
  the only place raw text hides inside an otherwise-parsed value — so it's
  blanked before comparing rather than compared as-is.
  """
  if call is None or call.announcement is None:
    return call
  return call.model_copy(
    update={'announcement': call.announcement.model_copy(update={'raw': ''})}
  )


def _auction_entry_signature(entry: AuctionEntry) -> object:
  """What voting compares for one auction entry: its meaning, not its raw
  transcription or issues.
  """
  return (
    _call_signature(entry.call),
    entry.by_opponents,
    entry.alerted,
    entry.flagged_for_discussion,
  )


def _lead_signature(lead: Lead | None) -> object:
  """What voting compares for the opening lead: the card and its discussion
  flag, not the raw transcription or issues.
  """
  return None if lead is None else (lead.card, lead.flagged_for_discussion)


def _outcome_signature(outcome: Outcome | None) -> object:
  """What voting compares for the contract cell: the resolution and its
  discussion flag, not the raw transcription or issues.
  """
  return (
    None
    if outcome is None
    else (outcome.resolution, outcome.flagged_for_discussion)
  )


def _vote_boards(board_a: Board, board_b: Board) -> Board:
  """Merge two runs' transcriptions of the same board.

  A cell where the runs agree is carried through unquestioned, arbitrarily from
  `board_a` — an agreeing cell is the same content either way. A cell where they
  disagree keeps `board_a`'s candidate but gains a `voting_disagreement` issue
  naming both raw readings, so the pipeline never silently guesses between two
  live candidates.
  """
  issues: list[Issue] = []

  if (board_a.number.schedule, board_a.flagged_for_review) != (
    board_b.number.schedule,
    board_b.flagged_for_review,
  ):
    issues.append(
      _voting_issue('board_number', board_a.number.raw, board_b.number.raw)
    )

  if len(board_a.auction) != len(board_b.auction):
    issues.append(
      Issue(
        code=_VOTING_DISAGREEMENT,
        severity=IssueSeverity.HIGH,
        message=(
          'the two extraction runs transcribed different auction lengths: '
          f'{len(board_a.auction)} vs {len(board_b.auction)} entries'
        ),
        location='auction',
      )
    )
  for index, (entry_a, entry_b) in enumerate(
    zip(board_a.auction, board_b.auction, strict=False)
  ):
    if _auction_entry_signature(entry_a) != _auction_entry_signature(entry_b):
      issues.append(
        _voting_issue(f'auction[{index}]', entry_a.raw, entry_b.raw)
      )

  if _lead_signature(board_a.opening_lead) != _lead_signature(
    board_b.opening_lead
  ):
    issues.append(
      _voting_issue(
        'opening_lead',
        board_a.opening_lead.raw if board_a.opening_lead else '',
        board_b.opening_lead.raw if board_b.opening_lead else '',
      )
    )

  if _outcome_signature(board_a.outcome) != _outcome_signature(board_b.outcome):
    issues.append(
      _voting_issue(
        'outcome',
        board_a.outcome.raw if board_a.outcome else '',
        board_b.outcome.raw if board_b.outcome else '',
      )
    )

  if board_a.notes != board_b.notes:
    issues.append(
      _voting_issue('notes', board_a.notes or '', board_b.notes or '')
    )

  if not issues:
    return board_a
  return board_a.model_copy(update={'issues': (*board_a.issues, *issues)})


def _vote_board_pair(board_a: Board | None, board_b: Board | None) -> Board:
  """Vote one position's board pair, handling a run that skipped it.

  A position present in only one run can't be voted at all: the lone board is
  kept — nothing is garbage — flagged `voting_uncorroborated_board` so it ranks
  for review rather than being trusted like an agreeing pair.
  """
  if board_a is None or board_b is None:
    lone = board_a if board_b is None else board_b
    assert lone is not None
    issue = Issue(
      code=_VOTING_UNCORROBORATED_BOARD,
      severity=IssueSeverity.HIGH,
      message='only one extraction run produced a board at this position',
    )
    return lone.model_copy(update={'issues': (*lone.issues, issue)})
  return _vote_boards(board_a, board_b)


def vote_sessions(session_a: Session, session_b: Session) -> Session:
  """Merge two runs' transcriptions of the same sheet into one `Session`.

  Both sessions must already be parsed and validated (via
  `assembly.parse_and_assemble_session`) — voting compares finished content, not
  raw JSON. `session_a`'s footer and source are the base; a footer disagreement
  and a board-count mismatch each become a session-level issue, and boards are
  voted position by position (see `_vote_board_pair`).
  """
  issues = list(session_a.issues)

  if session_a.event != session_b.event:
    issues.append(_voting_issue('event', session_a.event, session_b.event))
  if session_a.date != session_b.date:
    issues.append(
      _voting_issue(
        'date',
        session_a.date.isoformat() if session_a.date else '',
        session_b.date.isoformat() if session_b.date else '',
      )
    )

  boards_a, boards_b = session_a.boards, session_b.boards
  if len(boards_a) != len(boards_b):
    issues.append(
      Issue(
        code=_VOTING_BOARD_COUNT_MISMATCH,
        severity=IssueSeverity.HIGH,
        message=(
          'the two extraction runs transcribed different board counts: '
          f'{len(boards_a)} vs {len(boards_b)}'
        ),
      )
    )

  voted_boards = tuple(
    _vote_board_pair(board_a, board_b)
    for board_a, board_b in itertools.zip_longest(boards_a, boards_b)
  )
  return session_a.model_copy(
    update={'boards': voted_boards, 'issues': tuple(issues)}
  )
