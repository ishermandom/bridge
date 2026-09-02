# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for getting a scan from the inbox through extraction and onto disk.

Scans are drawn grids written to real temporary directories, and the model is a
scripted `run_command` fake — no `claude` process, and no committed scan, which
would carry member handwriting. The tree is real rather than faked for the
reason traveller_store_test's is: what these cover is a directory of files
moving, and the image pipeline reaches the disk below anything a filesystem fake
patches (see faking-the-filesystem.md).
"""

import datetime
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from PIL import Image

from session_analysis import board_rotation
from session_analysis.models import Board, BoardNumber, Schedule, Session
from session_analysis.private_paths import (
  CLUB_CAPTURE_DIRECTORY,
  PrivateTree,
)
from session_analysis.testing import provenance
from session_analysis.testing.scripted_model import ScriptedModelRunner
from session_analysis.testing.synthetic_scans import draw_sheet
from session_analysis.unreviewed.ingest import (
  ReconcileReport,
  ScanOutcome,
  ScanReport,
  SessionOutcome,
  match_pending_sessions,
  process_inbox,
  reconcile_pending_sessions,
  summarize_reconciliation,
  summarize_run,
)

# The name our row is matched on. No capture here names it — these cover the
# join running at all, not what it finds once it does.
OUR_NAME = 'First Last'

TESTDATA = Path(__file__).parent.parent / 'testdata/travellers'

# EXIF's top-level `DateTime`, which is what a PNG carries through a round trip.
_DATE_TIME = 306

# 29 rules bounding 28 board rows, unlike `draw_sheet`'s default 24 — so a test
# needing a second, differently-drawn scan has one whose bytes differ.
_TWENTY_EIGHT_ROWS = list(range(100, 661, 20))


def _write_scan(
  tree: PrivateTree,
  name: str,
  *,
  taken: datetime.date = datetime.date(2026, 7, 1),
  rule_ys: Sequence[int] | None = None,
) -> Path:
  """Draw a scan into the inbox, stating the day it was taken."""
  image = draw_sheet() if rule_ys is None else draw_sheet(rule_ys)
  exif = image.getexif()
  exif[_DATE_TIME] = f'{taken:%Y:%m:%d} 11:30:00'
  tree.scan_inbox.mkdir(parents=True, exist_ok=True)
  scan = tree.scan_inbox / name
  image.save(scan, exif=exif)
  return scan


def _sheet_json(
  *,
  event: str = 'PABC morn.',
  date: str = '6/29',
  boards: Sequence[Mapping[str, str]] = (),
) -> str:
  """One run's raw vision-model output, in the wire shape assembly reads."""
  return json.dumps(
    {'sheet': {'event': event, 'date': date, 'boards': list(boards)}}
  )


def _stored_session(tree: PrivateTree, stem: str) -> Session:
  """The pending record a run wrote, read back from disk."""
  record = tree.pending_session_records / f'{stem}.json'
  return Session.model_validate_json(record.read_text())


def _archived_scans(tree: PrivateTree) -> Sequence[Path]:
  """Every scan sitting in the archive."""
  return sorted(tree.scan_archive.iterdir())


def _write_pending_session(
  tree: PrivateTree,
  session_key: str,
  date: datetime.date,
  board_numbers: Sequence[int] = (),
) -> None:
  """Put a digitized session in the tree, as an earlier run would have.

  The boards carry a resolved number and nothing else: reconciliation joins on
  the number, and every field it fills is one the sheet never recorded.
  """
  tree.pending_session_records.mkdir(parents=True, exist_ok=True)
  record = tree.pending_session_records / f'{session_key}.json'
  record.write_text(
    Session(
      session_key=session_key,
      event='PABC morn.',
      date=date,
      source=provenance.sheet_source(),
      boards=tuple(_unenriched_board(number) for number in board_numbers),
    ).model_dump_json()
  )


def _unenriched_board(number: int) -> Board:
  """One sheet row, as it stands before any traveller has been joined to it."""
  return Board(
    number=BoardNumber(
      raw=str(number),
      schedule=Schedule(
        number=number,
        dealer=board_rotation.dealer_for_board(number),
        vulnerability=board_rotation.vulnerability_for_board(number),
      ),
    )
  )


# --- a scan becomes a record ---


def test_a_scan_is_filed_under_the_key_its_footer_names(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert (tree.pending_session_records / 'pabc-morn-2026-06-29.json').is_file()
  assert run.value[0].outcome == ScanOutcome.DIGITIZED


def test_the_record_carries_the_key_as_well_as_the_filename(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  session = _stored_session(tree, 'pabc-morn-2026-06-29')
  assert session.session_key == 'pabc-morn-2026-06-29'
  assert session.event == 'PABC morn.'


def test_the_footer_year_resolves_against_the_scan_not_today(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  # Scanned in January, of a sheet written the previous December. Resolving
  # `12/29` against today would put it a year out.
  _write_scan(tree, 'scan.png', taken=datetime.date(2026, 1, 5))

  with ScriptedModelRunner(
    [_sheet_json(date='12/29'), _sheet_json(date='12/29')]
  ) as runner:
    process_inbox(tree, run_command=runner)

  session = _stored_session(tree, 'pabc-morn-2025-12-29')
  assert session.date == datetime.date(2025, 12, 29)


def test_the_boards_the_model_read_reach_the_record(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')
  board = {
    'board_number': '7',
    'auction': '1N P 3N P P P',
    'contract': '3N N =',
    'lead': 'HQ',
    'notes': '',
  }

  with ScriptedModelRunner(
    [_sheet_json(boards=[board]), _sheet_json(boards=[board])]
  ) as runner:
    process_inbox(tree, run_command=runner)

  session = _stored_session(tree, 'pabc-morn-2026-06-29')
  assert len(session.boards) == 1
  assert session.boards[0].number.schedule
  assert session.boards[0].number.schedule.number == 7


# --- the scan itself moves ---


def test_a_digitized_scan_leaves_the_inbox_for_the_archive(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  assert list(tree.scan_inbox.iterdir()) == []
  # Named with an abbreviated content hash ahead of the scanner's own name, so a
  # rerun can find it by its bytes without opening anything.
  assert len(_archived_scans(tree)) == 1
  assert _archived_scans(tree)[0].name.endswith('-scan.png')


def test_the_record_points_at_the_archived_scan(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  session = _stored_session(tree, 'pabc-morn-2026-06-29')
  assert (tree.scan_archive / session.source.image.path).is_file()


def test_the_detected_grid_persists_on_the_record(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png', rule_ys=_TWENTY_EIGHT_ROWS)

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  frame = _stored_session(tree, 'pabc-morn-2026-06-29').source.image.frame
  # The grid the review UI reproduces the dewarped frame from, rather than
  # re-detecting it from the archived scan.
  assert len(frame.geometry.row_boxes) == 28
  assert frame.source_quad.top_left.y < 100


# --- running twice ---


def test_the_same_scan_dropped_in_again_costs_no_model_call(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  scan = _write_scan(tree, 'scan.png')
  original = scan.read_bytes()
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  (tree.scan_inbox / 'scan.png').write_bytes(original)
  # Scripted with no replies at all: a model call would exhaust it and raise.
  with ScriptedModelRunner([]) as runner:
    rerun = process_inbox(tree, run_command=runner)

  assert rerun.value[0].outcome == ScanOutcome.SKIPPED
  assert 'already archived' in rerun.value[0].detail


def test_the_same_scan_under_a_new_name_leaves_one_archived_copy(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  scan = _write_scan(tree, 'scan.png')
  original = scan.read_bytes()
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  # The same photograph, renamed on its way back in — a copy step or a re-sync.
  (tree.scan_inbox / 'scan-copy.png').write_bytes(original)
  with ScriptedModelRunner([]) as runner:
    process_inbox(tree, run_command=runner)

  assert list(tree.scan_inbox.iterdir()) == []
  # One copy, not two: identical bytes differing only in the name they arrived
  # under are not two scans.
  assert len(_archived_scans(tree)) == 1


def test_a_second_photograph_of_a_digitized_sheet_is_skipped(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'first.png')
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  # Different pixels, so a different content hash — but the same footer, which
  # is what says the two are one session.
  _write_scan(tree, 'second.png', rule_ys=_TWENTY_EIGHT_ROWS)
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    rerun = process_inbox(tree, run_command=runner)

  assert rerun.value[0].outcome == ScanOutcome.SKIPPED
  assert 'already digitized as pabc-morn-2026-06-29' in rerun.value[0].detail
  # One record, not two: the second photograph added nothing.
  assert len(list(tree.pending_session_records.iterdir())) == 1


def test_a_re_photographed_sheet_still_reaches_the_archive(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'first.png')
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  _write_scan(tree, 'second.png', rule_ys=_TWENTY_EIGHT_ROWS)
  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    process_inbox(tree, run_command=runner)

  # It is a scan of a session on hand, so it belongs with the rest — and it must
  # not stay in the inbox for the next run to spend another model call on.
  assert list(tree.scan_inbox.iterdir()) == []
  assert len(_archived_scans(tree)) == 2


# --- a footer that named nothing ---


def test_an_unreadable_footer_is_still_stored_under_a_hash_name(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner(
    [_sheet_json(event='', date=''), _sheet_json(event='', date='')]
  ) as runner:
    run = process_inbox(tree, run_command=runner)

  # Nothing is garbage: the session is stored and reviewable, just not named.
  assert run.value[0].outcome == ScanOutcome.DIGITIZED
  stored = list(tree.pending_session_records.iterdir())
  assert len(stored) == 1
  assert stored[0].name.startswith('unnamed-')


def test_an_unreadable_footer_is_flagged_for_review(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'scan.png')

  with ScriptedModelRunner(
    [_sheet_json(event='', date=''), _sheet_json(event='', date='')]
  ) as runner:
    process_inbox(tree, run_command=runner)

  stem = next(iter(tree.pending_session_records.iterdir())).stem
  session = _stored_session(tree, stem)
  assert session.session_key is None
  assert 'unnamed_session' in {issue.code for issue in session.issues}


def test_two_unreadable_footers_do_not_read_as_one_session(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _write_scan(tree, 'first.png')
  _write_scan(tree, 'second.png', rule_ys=_TWENTY_EIGHT_ROWS)

  blank = _sheet_json(event='', date='')
  with ScriptedModelRunner([blank, blank, blank, blank]) as runner:
    run = process_inbox(tree, run_command=runner)

  # Each unnamed record leads with its own content hash, so neither is mistaken
  # for a second photograph of the other.
  assert [report.outcome for report in run.value] == [
    ScanOutcome.DIGITIZED,
    ScanOutcome.DIGITIZED,
  ]
  assert len(list(tree.pending_session_records.iterdir())) == 2


# --- a scan that could not be digitized ---


def test_a_scan_that_is_no_image_is_set_aside_with_its_reason(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  tree.scan_inbox.mkdir(parents=True)
  (tree.scan_inbox / 'scan.png').write_text('not an image')

  with ScriptedModelRunner([]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert run.value[0].outcome == ScanOutcome.FAILED
  assert list(tree.scan_inbox.iterdir()) == []
  assert (tree.scan_failures / 'scan.png').is_file()
  sidecar = tree.scan_failures / 'scan.png.error'
  assert 'ScanDecodingError' in sidecar.read_text()


def test_a_scan_with_no_grid_to_find_is_set_aside(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  tree.scan_inbox.mkdir(parents=True)
  # A blank page: nothing for the dewarp pass to fit a grid to.
  Image.new('L', (600, 800), 255).save(tree.scan_inbox / 'scan.png')

  with ScriptedModelRunner([]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert run.value[0].outcome == ScanOutcome.FAILED
  assert (tree.scan_failures / 'scan.png').is_file()
  assert (tree.scan_failures / 'scan.png.error').is_file()


def test_a_failed_scan_does_not_stop_the_ones_behind_it(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  tree.scan_inbox.mkdir(parents=True)
  (tree.scan_inbox / 'a-broken.png').write_text('not an image')
  _write_scan(tree, 'b-good.png')

  with ScriptedModelRunner([_sheet_json(), _sheet_json()]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert [report.outcome for report in run.value] == [
    ScanOutcome.FAILED,
    ScanOutcome.DIGITIZED,
  ]


# --- what counts as a scan ---


def test_an_empty_inbox_reports_nothing(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  tree.scan_inbox.mkdir(parents=True)

  with ScriptedModelRunner([]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert run.value == ()
  assert not run.issues


def test_a_dotfile_in_the_inbox_is_not_a_scan(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  tree.scan_inbox.mkdir(parents=True)
  # `.DS_Store` rides along in any directory the Finder has been near.
  (tree.scan_inbox / '.DS_Store').write_bytes(b'\x00\x01')

  with ScriptedModelRunner([]) as runner:
    run = process_inbox(tree, run_command=runner)

  assert run.value == ()


def test_a_missing_inbox_is_an_error(tmp_path: Path) -> None:
  with pytest.raises(FileNotFoundError, match='no scan inbox'):
    process_inbox(PrivateTree(tmp_path))


# --- what the run prints ---


def test_the_summary_gives_every_scan_a_line() -> None:
  reports = [
    ScanReport('a.png', ScanOutcome.DIGITIZED, 'pabc-morn-2026-06-29'),
    ScanReport('b.png', ScanOutcome.SKIPPED, 'already archived'),
    ScanReport('c.png', ScanOutcome.FAILED, 'no grid could be resolved'),
  ]

  lines = list(summarize_run(reports))

  assert lines[0] == '3 scans in the inbox:'
  assert 'a.png — pabc-morn-2026-06-29' in lines[1]
  assert 'digitized' in lines[1]
  assert 'skipped' in lines[2]
  assert 'failed' in lines[3]


def test_a_single_scan_is_not_reported_in_the_plural() -> None:
  reports = [ScanReport('a.png', ScanOutcome.DIGITIZED, 'a-key')]

  assert next(iter(summarize_run(reports))) == '1 scan in the inbox:'


def test_an_empty_run_says_the_inbox_was_empty() -> None:
  assert list(summarize_run([])) == ['The inbox is empty.']


# --- a capture saved by hand ---


def test_a_capture_dropped_in_is_stored_and_matched(tmp_path: Path) -> None:
  tree = PrivateTree(tmp_path)
  # The acquisition fallback: a capture saved by hand, never fetched.
  capture = tree.traveller_captures / CLUB_CAPTURE_DIRECTORY / 'D260309M.pbn'
  capture.parent.mkdir(parents=True)
  capture.write_text((TESTDATA / 'club_game.pbn').read_text())
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9)
  )

  matched = match_pending_sessions(tree)

  (one,) = matched.value
  assert one.stem == 'pabc-morn-2026-03-09'
  assert [traveller.reference.path for traveller in one.travellers] == [
    f'{CLUB_CAPTURE_DIRECTORY}/D260309M.pbn'
  ]


def test_a_tree_holding_no_captures_yet_is_not_an_error(
  tmp_path: Path,
) -> None:
  # Scans and captures arrive by unrelated routes, so a tree can hold digitized
  # sessions and no captures at all — the first run on a new tree always does.
  tree = PrivateTree(tmp_path)
  _write_pending_session(
    tree, 'pabc-morn-2026-06-29', datetime.date(2026, 6, 29)
  )

  matched = match_pending_sessions(tree)

  (one,) = matched.value
  assert one.stem == 'pabc-morn-2026-06-29'
  assert one.travellers == ()
  assert not matched.issues


# --- a traveller reconciles the session it covers ---


def _drop_capture(tree: PrivateTree, name: str = 'D260309M.pbn') -> Path:
  """Save a club capture by hand, as the acquisition fallback does."""
  capture = tree.traveller_captures / CLUB_CAPTURE_DIRECTORY / name
  capture.parent.mkdir(parents=True, exist_ok=True)
  capture.write_text((TESTDATA / 'club_game.pbn').read_text())
  return capture


def _stored_record_of(tree: PrivateTree, capture: Path) -> Path:
  """The traveller record a capture was parsed into."""
  relative = capture.relative_to(tree.traveller_captures)
  return tree.traveller_records / f'{relative}.json'


def _reconcile(tree: PrivateTree) -> Sequence[ReconcileReport]:
  """One whole run of the two passes the ingest command makes after a scan."""
  return reconcile_pending_sessions(
    tree, match_pending_sessions(tree).value, our_name=OUR_NAME
  )


def test_a_matched_traveller_enriches_the_pending_record(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )

  reports = _reconcile(tree)

  assert [report.session for report in reports] == ['pabc-morn-2026-03-09']
  enriched = _stored_session(tree, 'pabc-morn-2026-03-09')
  # The deal is what no sheet records and every traveller carries.
  assert all(board.deal for board in enriched.boards)


def test_a_withdrawn_capture_takes_its_enrichment_back_off(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  capture = _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )
  _reconcile(tree)

  # The capture turned out to be a different session's and was taken away. The
  # record parsed from it stays behind — nothing prunes one whose capture is
  # gone — so the capture on disk is what says the traveller is still here.
  capture.unlink()
  assert _stored_record_of(tree, capture).is_file()
  reports = _reconcile(tree)

  # Named, not just counted: on a capture root gone missing altogether this
  # line is the only thing separating an accident from a real withdrawal.
  assert f'{CLUB_CAPTURE_DIRECTORY}/D260309M.pbn' in reports[0].detail
  assert 'taken back off' in reports[0].detail
  cleared = _stored_session(tree, 'pabc-morn-2026-03-09')
  assert not any(board.deal for board in cleared.boards)


def test_a_capture_that_cannot_be_placed_leaves_the_enrichment_alone(
  tmp_path: Path,
) -> None:
  # A second sheet from the same date turns the match ambiguous, so the capture
  # is placed on neither session. It was not withdrawn, though, so the session
  # it already enriched keeps what the earlier run wrote.
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )
  _reconcile(tree)

  _write_pending_session(
    tree, 'pabc-eve-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )

  (held,) = _reconcile(tree)
  assert held.session == 'pabc-morn-2026-03-09'
  assert held.outcome == SessionOutcome.HELD
  assert f'{CLUB_CAPTURE_DIRECTORY}/D260309M.pbn' in held.detail
  assert all(
    board.deal for board in _stored_session(tree, 'pabc-morn-2026-03-09').boards
  )


def test_a_rerun_over_unmoved_travellers_changes_nothing(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )
  _reconcile(tree)

  assert _reconcile(tree) == ()
  # Reported as unchanged because it is already joined, not because the join was
  # skipped or its work undone.
  assert all(
    board.deal for board in _stored_session(tree, 'pabc-morn-2026-03-09').boards
  )


def test_a_session_no_traveller_covers_is_left_alone(tmp_path: Path) -> None:
  # A sheet scanned before its results are published, which is the ordinary
  # state of a session for its first few days.
  tree = PrivateTree(tmp_path)
  _write_pending_session(
    tree, 'pabc-morn-2026-06-29', datetime.date(2026, 6, 29), (1, 2)
  )

  assert _reconcile(tree) == ()


def test_a_traveller_record_that_stopped_parsing_holds_the_enrichment(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )
  _reconcile(tree)

  # The stored record no longer validates, most likely written under an older
  # shape of the model. Matching drops it before it can be placed, but the
  # capture it was parsed from is untouched — nothing was withdrawn.
  stored = next(tree.traveller_records.rglob('*.json'))
  stored.write_text('{"source": "club_pbn"}')

  (held,) = _reconcile(tree)
  assert held.outcome == SessionOutcome.HELD
  kept = _stored_session(tree, 'pabc-morn-2026-03-09')
  assert all(board.deal for board in kept.boards)


def test_a_capture_that_broke_keeps_its_place_beside_one_that_did_not(
  tmp_path: Path,
) -> None:
  # Two captures of one game, only one of whose records still validates.
  # Rejoining over the survivor alone would take the other's contribution off a
  # record nothing was withdrawn from — the same loss as undoing the whole
  # enrichment, only quieter, since the run still reports a success.
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  recap = _drop_capture(tree, 'D260309M-recap.pbn')
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )
  _reconcile(tree)

  _stored_record_of(tree, recap).write_text('{"source": "club_pbn"}')

  (held,) = _reconcile(tree)
  assert held.outcome == SessionOutcome.HELD
  # Both citations survive: the run declined to rejoin rather than rewriting
  # the record from the capture that still parses.
  cited = _stored_session(tree, 'pabc-morn-2026-03-09').source.travellers
  assert len(cited) == 2


# --- reporting what the join did ---


def test_a_run_with_nothing_to_report_says_every_session_is_current() -> None:
  assert list(summarize_reconciliation([])) == [
    'Every pending session is up to date.'
  ]


def test_the_reconciliation_summary_names_each_session_it_reports() -> None:
  reports = [
    ReconcileReport(
      'pabc-morn-2026-03-09',
      SessionOutcome.RECONCILED,
      'enriched from 1 traveller',
    ),
    ReconcileReport(
      'pabc-eve-2026-03-09', SessionOutcome.HELD, 'cites club/D260309M.pbn'
    ),
  ]

  lines = list(summarize_reconciliation(reports))

  assert lines[0] == '2 sessions the join reports:'
  # The outcome column is padded to the widest of them, as the scan summary
  # pads its own, so the session keys line up to be read down.
  assert lines[1] == (
    '  reconciled  pabc-morn-2026-03-09 — enriched from 1 traveller'
  )
  assert (
    lines[2] == '  held        pabc-eve-2026-03-09 — cites club/D260309M.pbn'
  )


def test_a_single_session_is_not_reported_in_the_plural() -> None:
  reports = [
    ReconcileReport('pabc-morn-2026-03-09', SessionOutcome.RECONCILED, 'done')
  ]

  assert (
    next(iter(summarize_reconciliation(reports)))
    == '1 session the join reports:'
  )


def test_a_capture_naming_us_nowhere_is_said_out_loud(tmp_path: Path) -> None:
  # The shape a capture matched to the wrong session takes. It still fills the
  # deals in, so the count of enriched boards reads like an ordinary success —
  # the finding is the only thing at the console that says otherwise.
  tree = PrivateTree(tmp_path)
  _drop_capture(tree)
  _write_pending_session(
    tree, 'pabc-morn-2026-03-09', datetime.date(2026, 3, 9), (1, 2)
  )

  lines = list(summarize_reconciliation(_reconcile(tree)))

  assert any('traveller_never_names_us' in line for line in lines)
