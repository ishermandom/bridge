# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for deciding which digitized session a captured traveller belongs to.

The pairing itself is pure, so most of these build records in memory. The two
readers are what touch disk, and they use real temporary directories for the
reason traveller_store_test does — the subject is a directory tree.
"""

import datetime
from pathlib import Path

from session_analysis.models import CaptureReference, Session
from session_analysis.private_paths import PrivateTree
from session_analysis.testing import provenance
from session_analysis.travellers import Traveller, TravellerSource
from session_analysis.unreviewed.session_matching import (
  match_travellers,
  read_pending_sessions,
  read_stored_travellers,
)


def _make_traveller(
  capture: str, date: datetime.date | None, *, event: str = 'Monday Pairs'
) -> Traveller:
  """A stored traveller, carrying only what matching reads of it."""
  return Traveller(
    source=TravellerSource.CLUB_PBN,
    reference=CaptureReference(path=capture),
    event=event,
    date=date,
  )


def _make_session(
  session_key: str | None,
  date: datetime.date | None,
  *,
  content_hash: str = 'deadbeefcafe1234',
) -> Session:
  """A digitized session, carrying only what matching reads of it."""
  return Session(
    session_key=session_key,
    event='PABC morn.',
    date=date,
    source=provenance.sheet_source(content_hash=content_hash),
  )


# --- pairing a capture with its session ---


def test_a_traveller_matches_the_session_sharing_its_date() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers([traveller], [session])

  assert matched.value == {'club/D260629M.pbn': 'pabc-morn-2026-06-29'}
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

  assert matched.value == {
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

  assert matched.value == {'club/D260629M.pbn': 'pabc-morn-2026-06-29'}


def test_a_traveller_no_session_shares_a_date_with_is_left_alone() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  session = _make_session('pabc-morn-2026-07-06', datetime.date(2026, 7, 6))

  matched = match_travellers([traveller], [session])

  # Unmatched and unreported: a capture routinely arrives before its sheet is
  # scanned, so saying so every run would bury the reports that matter.
  assert matched.value == {}
  assert not matched.issues


def test_a_traveller_matching_two_sessions_is_reported_not_guessed() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  morning = _make_session(
    'pabc-morn-2026-06-29', datetime.date(2026, 6, 29), content_hash='aaaa1111'
  )
  afternoon = _make_session(
    'pabc-aft-2026-06-29', datetime.date(2026, 6, 29), content_hash='bbbb2222'
  )

  matched = match_travellers([traveller], [morning, afternoon])

  assert matched.value == {}
  assert [issue.code for issue in matched.issues] == ['ambiguous_session_match']
  assert 'pabc-aft-2026-06-29' in matched.issues[0].message


def test_a_capture_stating_no_date_is_reported() -> None:
  traveller = _make_traveller('club/D260629M.pbn', None)
  session = _make_session('pabc-morn-2026-06-29', datetime.date(2026, 6, 29))

  matched = match_travellers([traveller], [session])

  assert matched.value == {}
  assert [issue.code for issue in matched.issues] == ['undated_capture']


def test_a_session_whose_date_was_unreadable_takes_no_part() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  undated = _make_session('pabc-morn-2026-06-29', None)

  matched = match_travellers([traveller], [undated])

  assert matched.value == {}
  # No issue of its own: `parse_footer` already flagged the unreadable date, and
  # reporting it again here would count one bad footer twice.
  assert not matched.issues


def test_an_unnamed_session_is_matched_under_its_hash_name() -> None:
  traveller = _make_traveller('club/D260629M.pbn', datetime.date(2026, 6, 29))
  unnamed = _make_session(
    None, datetime.date(2026, 6, 29), content_hash='deadbeefcafe1234'
  )

  matched = match_travellers([traveller], [unnamed])

  assert matched.value == {'club/D260629M.pbn': 'unnamed-deadbeefcafe'}


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
