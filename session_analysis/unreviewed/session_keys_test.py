# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for naming a digitized session from what its sheet says."""

import datetime

from session_analysis.unreviewed.session_keys import (
  derive_session_key,
  record_stem,
  short_hash,
)

# --- deriving a key from the footer ---


def test_a_footer_event_and_date_become_one_key() -> None:
  key = derive_session_key('pabc morn', datetime.date(2026, 6, 29))

  assert key == 'pabc-morn-2026-06-29'


def test_case_and_punctuation_collapse_into_the_slug() -> None:
  key = derive_session_key('PABC morn.', datetime.date(2026, 6, 29))

  assert key == 'pabc-morn-2026-06-29'


def test_a_run_of_separators_becomes_a_single_hyphen() -> None:
  key = derive_session_key('PABC  --  aft!', datetime.date(2026, 6, 29))

  assert key == 'pabc-aft-2026-06-29'


def test_digits_in_the_event_survive_into_the_slug() -> None:
  key = derive_session_key('Unit 499 Sectional', datetime.date(2026, 3, 7))

  assert key == 'unit-499-sectional-2026-03-07'


def test_two_times_of_day_on_one_date_give_two_keys() -> None:
  date = datetime.date(2026, 6, 29)

  morning = derive_session_key('PABC morn.', date)
  afternoon = derive_session_key('PABC aft.', date)

  assert morning != afternoon


def test_a_blank_event_names_no_key() -> None:
  assert derive_session_key('', datetime.date(2026, 6, 29)) is None


def test_an_event_of_punctuation_alone_names_no_key() -> None:
  # Nothing survives normalization, so there is no slug to build a key from.
  assert derive_session_key('---', datetime.date(2026, 6, 29)) is None


def test_an_unreadable_date_names_no_key() -> None:
  assert derive_session_key('PABC morn.', None) is None


# --- what a record is called on disk ---


def test_a_named_session_is_filed_under_its_key() -> None:
  stem = record_stem('pabc-morn-2026-06-29', 'deadbeefcafe1234', 1)

  assert stem == 'pabc-morn-2026-06-29'


def test_an_unnamed_session_is_filed_under_its_content_hash() -> None:
  stem = record_stem(None, 'deadbeefcafe1234', 1)

  assert stem == 'unnamed-deadbeefcafe'


def test_two_unnamed_sessions_never_collide() -> None:
  # An unreadable footer must not read as "already digitized" — the content hash
  # is what keeps each unnamed record distinct.
  first = record_stem(None, 'deadbeefcafe1234', 1)
  second = record_stem(None, 'facefeed99991234', 1)

  assert first != second


def test_two_unnamed_sheets_from_one_container_never_collide() -> None:
  # Sheets scanned together share their file's bytes, so the hash alone names
  # the container rather than the sheet; the page is what tells them apart.
  first = record_stem(None, 'deadbeefcafe1234', 1)
  second = record_stem(None, 'deadbeefcafe1234', 2)

  assert first != second


def test_two_named_sheets_from_one_container_never_collide() -> None:
  # Two sessions of one event on one day derive the same key, so the page is
  # the only thing keeping their records apart.
  first = record_stem('pabc-morn-2026-06-29', 'deadbeefcafe1234', 1)
  second = record_stem('pabc-morn-2026-06-29', 'deadbeefcafe1234', 2)

  assert first == 'pabc-morn-2026-06-29'
  assert second == 'pabc-morn-2026-06-29-p2'


def test_the_short_hash_leaves_the_rest_of_a_name_readable() -> None:
  assert short_hash('deadbeefcafe1234567890') == 'deadbeefcafe'
