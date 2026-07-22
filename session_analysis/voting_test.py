# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for voting between two independent transcriptions of a sheet.

Sessions are built with `assembly.assemble_session` over raw board dicts, the
same way assembly_test.py does — that exercises the real parser rather than
hand-building `Board` objects field by field, so a test's two "runs" read like
the vision model's own output.
"""

import datetime
from collections.abc import Mapping

from session_analysis.assembly import RawSession, assemble_session
from session_analysis.models import Session, SheetImage, Source
from session_analysis.voting import vote_sessions

_REFERENCE_DATE = datetime.date(2026, 7, 1)


def _source() -> Source:
  return Source(image=SheetImage(path='sheet.jpg', content_hash='abc123'))


def _raw_board(**cells: str) -> Mapping[str, str]:
  defaults = {
    'board_number': '7',
    'auction': '',
    'contract': '',
    'lead': '',
    'notes': '',
  }
  return defaults | dict(cells)


def _session(
  *boards: object, event: str = 'PABC mon', date: str = '6/29'
) -> Session:
  raw = RawSession(event=event, date=date, boards=boards)
  return assemble_session(raw, _source(), reference_date=_REFERENCE_DATE)


def _issue_codes(session: Session) -> set[str]:
  """Every issue code anywhere in the session: its own plus every board's."""
  codes = {issue.code for issue in session.issues}
  for board in session.boards:
    codes |= {issue.code for issue in board.issues}
  return codes


# --- agreeing cells are carried through untouched ---


def test_identical_runs_produce_no_voting_issues() -> None:
  board = _raw_board(auction='1N', contract='1N N +1', lead='2S', notes='ok')

  merged = vote_sessions(_session(board), _session(board))

  assert not _issue_codes(merged) & {
    'voting_disagreement',
    'voting_board_count_mismatch',
    'voting_uncorroborated_board',
  }


def test_double_notation_case_is_not_a_disagreement() -> None:
  # 'x' and 'X' both parse to the same `Call(kind=DOUBLE)` — different raw text,
  # same meaning, so voting must not flag it.
  session_a = _session(_raw_board(auction='1H x'))
  session_b = _session(_raw_board(auction='1H X'))

  merged = vote_sessions(session_a, session_b)

  assert 'voting_disagreement' not in _issue_codes(merged)


def test_notrump_range_marker_order_is_not_a_disagreement() -> None:
  # `1N^0_2` and `1N_2^0` both parse to the same 10-12 notrump range, but the
  # underlying `Announcement.raw` text differs ('^0_2' vs '_2^0') — this is the
  # nested-raw case voting must strip before comparing.
  session_a = _session(_raw_board(auction='1N^0_2'))
  session_b = _session(_raw_board(auction='1N_2^0'))

  merged = vote_sessions(session_a, session_b)

  assert 'voting_disagreement' not in _issue_codes(merged)


# --- disagreeing cells are flagged, one per cell ---


def test_a_different_bid_is_flagged_as_a_disagreement() -> None:
  session_a = _session(_raw_board(auction='1H'))
  session_b = _session(_raw_board(auction='1S'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'auction[0]'
  assert '1H' in issue.message and '1S' in issue.message


def test_different_auction_lengths_are_flagged_once_not_per_entry() -> None:
  session_a = _session(_raw_board(auction='1H P'))
  session_b = _session(_raw_board(auction='1H'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  voting_issues = [i for i in board.issues if i.code == 'voting_disagreement']
  assert [i.location for i in voting_issues] == ['auction']
  assert '2' in voting_issues[0].message and '1' in voting_issues[0].message


def test_a_disagreeing_lead_is_flagged() -> None:
  session_a = _session(_raw_board(lead='2S'))
  session_b = _session(_raw_board(lead='3S'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'opening_lead'


def test_a_disagreeing_contract_is_flagged() -> None:
  session_a = _session(_raw_board(contract='1N N +1'))
  session_b = _session(_raw_board(contract='1N N +2'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'outcome'


def test_disagreeing_notes_are_flagged() -> None:
  session_a = _session(_raw_board(notes='nice defense'))
  session_b = _session(_raw_board(notes='great defense'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'notes'


def test_a_disagreeing_board_number_is_flagged() -> None:
  session_a = _session(_raw_board(board_number='7'))
  session_b = _session(_raw_board(board_number='8'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'board_number'


def test_a_circle_mark_disagreement_is_flagged() -> None:
  session_a = _session(_raw_board(board_number='(7)'))
  session_b = _session(_raw_board(board_number='7'))

  merged = vote_sessions(session_a, session_b)

  (board,) = merged.boards
  (issue,) = [i for i in board.issues if i.code == 'voting_disagreement']
  assert issue.location == 'board_number'


# --- structural mismatches ---


def test_an_extra_board_is_kept_and_flagged_uncorroborated() -> None:
  session_a = _session(
    _raw_board(board_number='7'), _raw_board(board_number='8')
  )
  session_b = _session(_raw_board(board_number='7'))

  merged = vote_sessions(session_a, session_b)

  assert len(merged.boards) == 2
  assert 'voting_board_count_mismatch' in _issue_codes(merged)
  extra_board = merged.boards[1]
  assert 'voting_uncorroborated_board' in {i.code for i in extra_board.issues}
  # The board both runs agree on votes normally, with no disagreement issue.
  assert 'voting_disagreement' not in {i.code for i in merged.boards[0].issues}


def test_a_footer_disagreement_is_flagged_at_the_session_level() -> None:
  session_a = _session(_raw_board(), event='PABC mon', date='6/29')
  session_b = _session(_raw_board(), event='PABC Mon', date='6/30')

  merged = vote_sessions(session_a, session_b)

  locations = {
    issue.location
    for issue in merged.issues
    if issue.code == 'voting_disagreement'
  }
  assert locations == {'event', 'date'}
