# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for deciding which digitized session a captured traveller belongs to.

The pairing itself is pure, so most of these build records in memory. The two
readers are what touch disk, and they use real temporary directories for the
reason traveller_store_test does — the subject is a directory tree.
"""

import datetime
from collections.abc import Sequence
from pathlib import Path

from session_analysis import board_rotation
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Rank,
  Strain,
  Suit,
)
from session_analysis.models import (
  Board,
  BoardNumber,
  CaptureReference,
  Card,
  Contract,
  Deal,
  Lead,
  Outcome,
  PlayedContract,
  Result,
  Schedule,
  Session,
)
from session_analysis.private_paths import PrivateTree
from session_analysis.testing import deals, provenance
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerSource,
)
from session_analysis.unreviewed.session_matching import (
  match_travellers,
  read_pending_sessions,
  read_stored_travellers,
)


def _make_traveller(
  capture: str,
  date: datetime.date | None,
  *,
  event: str = 'Monday Pairs',
  board_deals: Sequence[Deal] = (),
) -> Traveller:
  """A stored traveller, carrying only what matching reads of it.

  `board_deals` holds one deal per board, numbered from board 1.
  """
  return Traveller(
    source=TravellerSource.CLUB_PBN,
    reference=CaptureReference(path=capture),
    event=event,
    date=date,
    boards=tuple(
      TravellerBoard(number=number, deal=deal)
      for number, deal in enumerate(board_deals, start=1)
    ),
  )


def _make_session(
  session_key: str | None,
  date: datetime.date | None,
  *,
  content_hash: str = 'deadbeefcafe1234',
  leads_from_west: Sequence[Card] = (),
) -> Session:
  """A digitized session, carrying only what matching reads of it.

  `leads_from_west` holds one opening lead per board, numbered from board 1.
  South declares every board, which is what puts West on lead.
  """
  return Session(
    session_key=session_key,
    event='PABC morn.',
    date=date,
    source=provenance.sheet_source(content_hash=content_hash),
    boards=tuple(
      _make_board_led_from_west(number, lead)
      for number, lead in enumerate(leads_from_west, start=1)
    ),
  )


def _make_board_led_from_west(number: int, lead: Card) -> Board:
  """One sheet row: South played three notrump, and West led `lead`."""
  return Board(
    number=BoardNumber(
      raw=str(number),
      schedule=Schedule(
        number=number,
        dealer=board_rotation.dealer_for_board(number),
        vulnerability=board_rotation.vulnerability_for_board(number),
      ),
    ),
    outcome=Outcome(
      raw='3NS=',
      resolution=PlayedContract(
        contract=Contract(
          level=3,
          strain=Strain.NOTRUMP,
          declarer=Direction.SOUTH,
          penalty=Penalty.NONE,
        ),
        result=Result(tricks_taken=9),
      ),
    ),
    opening_lead=Lead(raw=f'{lead.rank}{lead.suit}', card=lead),
  )


# --- pairing a capture with its session ---


def test_a_traveller_matches_the_session_sharing_its_date() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers([traveller], [session])

  assert matched.value.sessions == {'club/D260629M.pbn': 'pabc-morn-2026-06-29'}
  assert not matched.issues


def test_every_capture_of_one_session_matches_it() -> None:
  # A club game publishes a PBN and an HTML recap, and ACBL publishes its own
  # copy; all three are captures of the one session.
  captures = [
    _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29)),
    _make_traveller('club/R260629M.htm', datetime.date(2026, 6, 29)),
    _make_traveller('acbl_club/1441256.html', datetime.date(2026, 6, 29)),
  ]
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers(captures, [session])

  assert matched.value.sessions == {
    'club/D260629M.pbn': 'pabc-morn-2026-06-29',
    'club/R260629M.htm': 'pabc-morn-2026-06-29',
    'acbl_club/1441256.html': 'pabc-morn-2026-06-29',
  }


def test_the_event_name_never_has_to_agree() -> None:
  # Every source spells one session's event its own way, so the names differ on
  # a true match as often as on a false one — only the date is compared.
  traveller = _make_traveller(
    'club/D260629M.pbn',
    datetime.date(2026, 6, 29),
    event="John & Will's Monday Bridge",
  )
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers([traveller], [session])

  assert matched.value.sessions == {'club/D260629M.pbn': 'pabc-morn-2026-06-29'}


def test_a_traveller_no_session_shares_a_date_with_is_left_alone() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  session = _make_session('pabc-morn-2026-07-06', datetime.date(2026, 7, 6))

  matched = match_travellers([traveller], [session])

  # Unmatched and unreported: a capture routinely arrives before its sheet is
  # scanned, so saying so every run would bury the reports that matter. The
  # session still reports that no capture of its own date is stored, so the
  # check is only that nothing names this capture.
  assert matched.value.sessions == {}
  assert not any('club/D260629M.pbn' in one.message for one in matched.issues)


def test_a_traveller_matching_two_sessions_is_reported_not_guessed() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  morning = _make_session(
    'pabc-morn-2026-06-29', datetime.date(2026, 6, 29), content_hash='aaaa1111'
  )
  afternoon = _make_session(
    'pabc-aft-2026-06-29', datetime.date(2026, 6, 29), content_hash='bbbb2222'
  )

  matched = match_travellers([traveller], [morning, afternoon])

  assert matched.value.sessions == {}
  # Reported once, against the capture: the two sessions it leaves uncovered are
  # not reported over again.
  assert [issue.code for issue in matched.issues] == ['ambiguous_session_match']
  assert 'pabc-aft-2026-06-29' in matched.issues[0].message


def test_a_capture_stating_no_date_is_reported() -> None:
  traveller = _make_traveller('club/D260629M.pbn', None)
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers([traveller], [session])

  assert matched.value.sessions == {}
  # Beside the session's own report that no capture of its date is stored.
  assert 'undated_capture' in [issue.code for issue in matched.issues]


def test_a_session_whose_date_was_unreadable_takes_no_part() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  undated = _make_session('pabc-morn-2026-06-29', None)

  matched = match_travellers([traveller], [undated])

  assert matched.value.sessions == {}
  # No issue of its own: `parse_footer` already flagged the unreadable date, and
  # reporting it again here would count one bad footer twice.
  assert not matched.issues


def test_an_unnamed_session_is_matched_under_its_hash_name() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  unnamed = _make_session(
    None, datetime.date(2026, 6, 29), content_hash='deadbeefcafe1234'
  )

  matched = match_travellers([traveller], [unnamed])

  assert matched.value.sessions == {'club/D260629M.pbn': 'unnamed-deadbeefcafe'}


# --- telling apart the games played on one date ---


def test_a_capture_whose_deals_contradict_the_leads_is_ruled_out() -> None:
  # The club published two games that day, and this is the one we did not play.
  # West's only club in `a_deal_the_lead_decides` is the two, so none of these
  # club leads could have come from West's hand.
  afternoon_game = _make_traveller(
    'club/D260915A.pbn',
    datetime.date(2026, 9, 15),
    board_deals=[deals.a_deal_the_lead_decides()] * 3,
  )
  session = _make_session(
    'pabc-morn-2026-09-15',
    datetime.date(2026, 9, 15),
    leads_from_west=[
      Card(rank=Rank.ACE, suit=Suit.CLUBS),
      Card(rank=Rank.KING, suit=Suit.CLUBS),
      Card(rank=Rank.QUEEN, suit=Suit.CLUBS),
    ],
  )

  matched = match_travellers([afternoon_game], [session])

  assert matched.value.sessions == {}
  assert matched.value.ruled_out == {'club/D260915A.pbn'}


def test_the_leads_send_each_capture_of_a_date_to_its_own_session() -> None:
  # In `a_suit_to_each_seat` West holds every club and no heart; in
  # `a_deal_the_lead_decides` West holds the top hearts and only the two of
  # clubs. So the club leads fit only the morning game's deals, and the heart
  # leads only the afternoon game's.
  morning_game = _make_traveller(
    'club/D260915M.pbn',
    datetime.date(2026, 9, 15),
    board_deals=[deals.a_suit_to_each_seat()] * 2,
  )
  afternoon_game = _make_traveller(
    'club/D260915A.pbn',
    datetime.date(2026, 9, 15),
    board_deals=[deals.a_deal_the_lead_decides()] * 2,
  )
  morning = _make_session(
    'pabc-morn-2026-09-15',
    datetime.date(2026, 9, 15),
    content_hash='aaaa1111',
    leads_from_west=[
      Card(rank=Rank.ACE, suit=Suit.CLUBS),
      Card(rank=Rank.KING, suit=Suit.CLUBS),
    ],
  )
  afternoon = _make_session(
    'pabc-aft-2026-09-15',
    datetime.date(2026, 9, 15),
    content_hash='bbbb2222',
    leads_from_west=[
      Card(rank=Rank.ACE, suit=Suit.HEARTS),
      Card(rank=Rank.KING, suit=Suit.HEARTS),
    ],
  )

  matched = match_travellers(
    [morning_game, afternoon_game], [morning, afternoon]
  )

  assert matched.value.sessions == {
    'club/D260915M.pbn': 'pabc-morn-2026-09-15',
    'club/D260915A.pbn': 'pabc-aft-2026-09-15',
  }
  assert not matched.issues


def test_a_capture_failing_one_misread_lead_still_matches() -> None:
  # West holds no heart in `a_suit_to_each_seat`, so the heart lead is
  # impossible, as a misread card on the sheet would be. One failed lead in four
  # stays under the tolerated third, while another game's deals fail about three
  # in four.
  capture = _make_traveller(
    'club/D260915M.pbn',
    datetime.date(2026, 9, 15),
    board_deals=[deals.a_suit_to_each_seat()] * 4,
  )
  session = _make_session(
    'pabc-morn-2026-09-15',
    datetime.date(2026, 9, 15),
    leads_from_west=[
      Card(rank=Rank.ACE, suit=Suit.CLUBS),
      Card(rank=Rank.KING, suit=Suit.CLUBS),
      Card(rank=Rank.ACE, suit=Suit.HEARTS),
      Card(rank=Rank.QUEEN, suit=Suit.CLUBS),
    ],
  )

  matched = match_travellers([capture], [session])

  assert matched.value.sessions == {'club/D260915M.pbn': 'pabc-morn-2026-09-15'}
  assert matched.value.ruled_out == frozenset()


def test_a_capture_stating_no_deals_is_placed_by_its_date_alone() -> None:
  # With no deal to check the leads against, nothing argues for another game.
  capture = _make_traveller('club/R260915M.htm', datetime.date(2026, 9, 15))
  session = _make_session(
    'pabc-morn-2026-09-15',
    datetime.date(2026, 9, 15),
    leads_from_west=[Card(rank=Rank.ACE, suit=Suit.HEARTS)],
  )

  matched = match_travellers([capture], [session])

  assert matched.value.sessions == {'club/R260915M.htm': 'pabc-morn-2026-09-15'}


# --- reporting a session no capture covers ---


def test_a_session_no_capture_of_its_date_fits_is_reported_high() -> None:
  # The shape a badly misread sheet takes once it rules out its own game's
  # capture. The capture itself goes unreported, so this issue is the only sign.
  ruled_out_game = _make_traveller(
    'club/D260915M.pbn',
    datetime.date(2026, 9, 15),
    board_deals=[deals.a_deal_the_lead_decides()] * 3,
  )
  session = _make_session(
    'pabc-morn-2026-09-15',
    datetime.date(2026, 9, 15),
    leads_from_west=[
      Card(rank=Rank.ACE, suit=Suit.CLUBS),
      Card(rank=Rank.KING, suit=Suit.CLUBS),
      Card(rank=Rank.QUEEN, suit=Suit.CLUBS),
    ],
  )

  matched = match_travellers([ruled_out_game], [session])

  assert [issue.code for issue in matched.issues] == ['no_capture_of_date_fits']
  assert matched.issues[0].severity == IssueSeverity.HIGH
  assert 'pabc-morn-2026-09-15' in matched.issues[0].message


def test_a_session_with_no_stored_capture_of_its_date_is_reported_low() -> None:
  # Most often a sheet scanned before its results were fetched.
  session = _make_session('pabc-morn-2026-09-15', datetime.date(2026, 9, 15))

  matched = match_travellers([], [session])

  assert [issue.code for issue in matched.issues] == [
    'no_capture_of_date_stored'
  ]
  assert matched.issues[0].severity == IssueSeverity.LOW
  assert 'pabc-morn-2026-09-15' in matched.issues[0].message


# --- reading the records off disk ---


def test_stored_travellers_are_read_back_from_the_records_root(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  record = tree.traveller_records / 'club/D260629M.pbn.json'
  record.parent.mkdir(parents=True)
  record.write_text(
    _make_traveller(
      'club/D260629M.pbn', datetime.date(2026, 6, 29)
    ).model_dump_json()
  )

  read = read_stored_travellers(tree)

  assert [one.reference.path for one in read.value] == ['club/D260629M.pbn']
  assert not read.issues


def test_a_record_that_no_longer_parses_is_reported_and_skipped(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  records = tree.traveller_records
  records.mkdir(parents=True)
  (records / 'stale.json').write_text('{"source": "who knows"}')
  (records / 'good.json').write_text(
    _make_traveller(
      'club/D260629M.pbn', datetime.date(2026, 6, 29)
    ).model_dump_json()
  )

  read = read_stored_travellers(tree)

  # The good record still takes part; only the stale one is set aside.
  assert [one.reference.path for one in read.value] == ['club/D260629M.pbn']
  assert [issue.code for issue in read.issues] == ['unreadable_record']


def test_a_records_root_that_does_not_exist_is_not_an_error(
  tmp_path: Path,
) -> None:
  read = read_stored_travellers(PrivateTree(tmp_path))

  assert read.value == ()
  assert not read.issues


def test_pending_sessions_are_read_from_the_pending_directory(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  tree.pending_session_records.mkdir(parents=True)
  record = tree.pending_session_records / 'pabc-morn-2026-06-29.json'
  record.write_text(
    _make_session(
      'pabc-morn-2026-06-29', datetime.date(2026, 6, 29)
    ).model_dump_json()
  )

  read = read_pending_sessions(tree)

  assert [one.session_key for one in read.value] == ['pabc-morn-2026-06-29']
