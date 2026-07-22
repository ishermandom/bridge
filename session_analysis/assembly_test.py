# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for assembling a whole sheet into a canonical `Session`.

These pin the composition layer: how the vision model's flat per-board output is
driven through the per-cell parsers into the canonical record, how blank cells
become absent values rather than spurious issues, and how a malformed board is
contained without costing the rest of the session. The per-cell parsing itself
is the parser's behaviour, tested in parsing_test.py.
"""

import datetime
from collections.abc import Mapping

from session_analysis.assembly import (
  RawSession,
  assemble_session,
  parse_and_assemble_session,
  parse_and_assemble_voted_session,
)
from session_analysis.enums import Rank, Strain, Suit
from session_analysis.models import (
  Card,
  PlayedContract,
  Session,
  SheetImage,
  Source,
)

# A fixed scan date: the sample sheets are from June, comfortably in the past of
# this reference, so a `6/29` footer resolves to the same calendar year.
_REFERENCE_DATE = datetime.date(2026, 7, 1)


def _source() -> Source:
  """Minimal provenance for tests that don't assert on the source."""
  return Source(image=SheetImage(path='sheet.jpg', content_hash='abc123'))


def _raw_board(**cells: str) -> Mapping[str, str]:
  """A raw board object, unspecified cells blank and the number defaulted.

  Callers pass only the cells a test asserts on; `board_number` defaults to a
  readable value for tests that don't care about it, and is passed explicitly by
  those that do.
  """
  defaults = {
    'board_number': '7',
    'auction': '',
    'contract': '',
    'lead': '',
    'notes': '',
  }
  return defaults | dict(cells)


def _assemble(
  *boards: object,
  event: str = 'PABC mon',
  date: str = '6/29',
  reference_date: datetime.date = _REFERENCE_DATE,
) -> Session:
  """Assemble a session from the given raw boards, with a throwaway source."""
  raw = RawSession(event=event, date=date, boards=boards)
  return assemble_session(raw, _source(), reference_date=reference_date)


# --- a well-formed board composes into all its parsed cells ---


def test_a_well_formed_board_composes_into_its_parsed_cells() -> None:
  session = _assemble(
    _raw_board(
      board_number='7',
      auction='(1N) 2H!',
      contract='2H S +2',
      lead='10S',
      notes='nice defense',
    )
  )

  (board,) = session.boards
  assert board.number.schedule is not None
  assert board.number.schedule.number == 7
  assert board.opening_lead is not None
  assert board.opening_lead.card == Card(rank=Rank.TEN, suit=Suit.SPADES)
  assert board.outcome is not None
  assert isinstance(board.outcome.resolution, PlayedContract)
  assert board.outcome.resolution.contract.strain == Strain.HEARTS
  # `(1N) 2H!`: the circled opening bid, then the alerted response.
  assert len(board.auction) == 2
  assert board.auction[0].by_opponents
  assert board.auction[1].alerted
  assert board.notes == 'nice defense'


def test_session_footer_is_carried_onto_the_session() -> None:
  session = _assemble(_raw_board(), event='PABC mon', date='6/29')

  assert session.event == 'PABC mon'
  assert session.date == datetime.date(2026, 6, 29)


# --- blank cells become absent values, not issues ---


def test_a_blank_lead_leaves_the_opening_lead_absent() -> None:
  session = _assemble(_raw_board(lead=''))

  (board,) = session.boards
  assert board.opening_lead is None


def test_a_blank_contract_leaves_the_outcome_absent() -> None:
  session = _assemble(_raw_board(contract=''))

  (board,) = session.boards
  assert board.outcome is None


def test_a_blank_auction_yields_no_entries() -> None:
  session = _assemble(_raw_board(auction=''))

  (board,) = session.boards
  assert board.auction == ()


def test_blank_notes_are_dropped_to_none() -> None:
  session = _assemble(_raw_board(notes='   '))

  (board,) = session.boards
  assert board.notes is None


# --- review flags and unreadable cells ---


def test_a_circled_board_number_flags_the_board_for_review() -> None:
  session = _assemble(_raw_board(board_number='(7)'))

  (board,) = session.boards
  assert board.flagged_for_review
  # The parentheses are the circle, not part of the number: 7, not "(7)".
  assert board.number.schedule is not None
  assert board.number.schedule.number == 7


def test_an_unreadable_board_number_is_kept_with_an_issue() -> None:
  session = _assemble(_raw_board(board_number='l3'))

  (board,) = session.boards
  assert board.number.schedule is None
  assert board.number.issues  # the board is stored, not dropped


def test_an_unreadable_date_becomes_a_session_issue() -> None:
  session = _assemble(_raw_board(), date='not a date')

  assert session.date is None
  assert session.issues


def test_a_session_missing_its_footer_still_assembles() -> None:
  # A botched footer — no `event` or `date` keys at all — must not drop the
  # boards. This exercises the JSON boundary directly, the way extraction will.
  raw = RawSession.model_validate({'boards': [{'board_number': '7'}]})

  session = assemble_session(raw, _source(), reference_date=_REFERENCE_DATE)

  assert session.date is None  # unreadable, not a crash
  assert session.issues  # surfaced at the session level
  assert len(session.boards) == 1  # the board survived


# --- errors stay contained to the smallest scope ---


def test_a_board_missing_its_number_keeps_its_other_cells() -> None:
  # A missing number must not wipe the board: contain the error to the number
  # cell, and still parse the lead and contract that were recorded.
  session = _assemble({'lead': '10S', 'contract': '2H S +2'})

  (board,) = session.boards
  assert board.number.schedule is None  # the number is unreadable
  assert board.number.issues
  assert board.opening_lead is not None  # ...but the lead still parsed
  assert board.opening_lead.card == Card(rank=Rank.TEN, suit=Suit.SPADES)


def test_a_numeric_board_number_is_coerced_not_dropped() -> None:
  # The model may emit a bare number as a JSON number rather than a string;
  # coercing it contains the type slip to the number cell, keeping the board.
  session = _assemble({'board_number': 7, 'lead': '10S'})

  (board,) = session.boards
  assert board.number.schedule is not None
  assert board.number.schedule.number == 7
  assert board.opening_lead is not None  # the board survived intact


def test_a_non_object_board_is_contained_without_losing_the_session() -> None:
  # A raw board that isn't an object at all can't be salvaged, but it must not
  # cost the well-formed board beside it.
  session = _assemble('garbage', _raw_board(board_number='8'))

  malformed, good = session.boards
  assert malformed.number.issues
  assert malformed.number.schedule is None
  assert good.number.schedule is not None
  assert good.number.schedule.number == 8


# --- provenance the vision model never sees ---


def test_the_source_is_carried_onto_the_session() -> None:
  source = Source(image=SheetImage(path='scan.jpg', content_hash='deadbeef'))
  raw = RawSession(event='PABC mon', date='6/29', boards=())

  session = assemble_session(raw, source, reference_date=_REFERENCE_DATE)

  assert session.source == source


# --- the JSON entry point ---


def test_well_formed_json_assembles_into_a_session() -> None:
  raw_json = (
    '{"sheet": {"event": "PABC mon", "date": "6/29", '
    '"boards": [{"board_number": "7", "lead": "10S"}]}}'
  )

  session = parse_and_assemble_session(
    raw_json, _source(), reference_date=_REFERENCE_DATE
  )

  assert session.event == 'PABC mon'
  (board,) = session.boards
  assert board.number.schedule is not None
  assert board.number.schedule.number == 7


def test_the_json_entry_point_also_runs_validation() -> None:
  # A played board with no auction transcribed should come back flagged, the
  # same way `validate_session` flags it directly — the JSON entry point must
  # not skip the validation pass.
  raw_json = (
    '{"sheet": {"boards": '
    '[{"board_number": "7", "contract": "4S N +6", "lead": "10S"}]}}'
  )

  session = parse_and_assemble_session(
    raw_json, _source(), reference_date=_REFERENCE_DATE
  )

  (board,) = session.boards
  assert 'auction_missing' in {issue.code for issue in board.issues}


def test_a_non_object_top_level_json_is_contained_as_a_session_issue() -> None:
  # `RawSheet.model_validate_json` has nothing to hand `assemble_session` when
  # the top level isn't an object at all; contain it here rather than raising.
  session = parse_and_assemble_session(
    '"garbage"', _source(), reference_date=_REFERENCE_DATE
  )

  assert session.boards == ()
  assert [issue.code for issue in session.issues] == ['malformed_session']


def test_a_missing_sheet_envelope_is_contained_as_a_session_issue() -> None:
  # Output that skips the `sheet` envelope is malformed, not an empty session —
  # `RawSheet.sheet` has no default precisely so this cannot pass silently.
  session = parse_and_assemble_session(
    '{"event": "PABC mon", "date": "6/29", "boards": []}',
    _source(),
    reference_date=_REFERENCE_DATE,
  )

  assert session.boards == ()
  assert [issue.code for issue in session.issues] == ['malformed_session']


def test_a_non_list_boards_field_is_contained_as_a_session_issue() -> None:
  session = parse_and_assemble_session(
    '{"sheet": {"boards": "not-a-list"}}',
    _source(),
    reference_date=_REFERENCE_DATE,
  )

  assert session.boards == ()
  assert [issue.code for issue in session.issues] == ['malformed_session']


# --- the two-run voting entry point ---


def test_agreeing_runs_assemble_with_no_voting_issues() -> None:
  raw_json = (
    '{"sheet": {"event": "PABC mon", "date": "6/29", '
    '"boards": [{"board_number": "7", "lead": "10S"}]}}'
  )

  session = parse_and_assemble_voted_session(
    raw_json, raw_json, _source(), reference_date=_REFERENCE_DATE
  )

  (board,) = session.boards
  assert board.number.schedule is not None
  assert board.number.schedule.number == 7
  assert 'voting_disagreement' not in {issue.code for issue in board.issues}


def test_disagreeing_runs_are_flagged_by_the_voting_entry_point() -> None:
  raw_json_a = '{"sheet": {"boards": [{"board_number": "7", "lead": "10S"}]}}'
  raw_json_b = '{"sheet": {"boards": [{"board_number": "7", "lead": "2S"}]}}'

  session = parse_and_assemble_voted_session(
    raw_json_a, raw_json_b, _source(), reference_date=_REFERENCE_DATE
  )

  (board,) = session.boards
  disagreements = [i for i in board.issues if i.code == 'voting_disagreement']
  assert [i.location for i in disagreements] == ['opening_lead']
