# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Getting a scan from the inbox through extraction and onto disk.

This is the stage that runs the pipeline end to end for the first time: a file
lands in `scoresheets/inbox/`, and what comes out is a validated `Session` in
`sessions/pending/`, with the scan itself moved into `scoresheets/archive/`.
Everything upstream of here reads images or strings; nothing before this wrote a
record.

The trigger is an explicit command rather than a watcher (spec.md `#ingest`). At
a game or two a week, a daemon debugged twice a year costs more than a one-tap
run — and a failure a person is looking at is worth more than one a log file
absorbs. That shapes what this module owes its caller: every scan ends the run
accounted for, as digitized, skipped, or failed, and no scan stays in the inbox
for the next run to re-spend a model call on.

A run is idempotent on two different keys, known at two different moments:

- The **content hash** is known before extraction. A file dropped in twice is
  recognized from its bytes and costs no model call at all.
- The **session key** the footer names is known only after extraction. It
  catches a fresh photograph of a sheet already digitized — different bytes,
  same session. That one necessarily costs a model call before it can be
  spotted; there is nothing in the file to recognize beforehand.

The second doubles as the collision rule. Two records cannot share a key,
because a second sheet claiming a key already taken is exactly what "this
session is already digitized" looks like — so it is reported and skipped rather
than given a disambiguating suffix. Two sheets of *one* container never collide
in the first place: they were fed to the scanner together, so they are different
sheets whatever their footers say, and `session_keys.record_stem` gives each
page after the first a suffix of its own.

The suffix puts those pages beyond the collision rule's reach. A sheet already
digitized alone, re-scanned later as the second page of some container, derives
a stem no stored record holds and is digitized again — two records for one
session, and a model call paid twice. This is left alone: it takes a sheet
re-scanned *and* bundled with others, the result is two visible records rather
than a silent loss, and the alternative is a duplicate check that has to know
which stems came from which bytes.

A file that yielded no readable sheet at all moves to `scoresheets/failed/` with
a sidecar naming what went wrong, as does one whose model call failed outright.
Terminal rather than staging: leaving it in the inbox would re-spend a model
call every run, and a directory of files with no explanation beside them is not
the loud failure this stage is supposed to produce. A container that yielded
some readable sheets is archived instead, since their records name it — with the
same sidecar beside it there, because the sheets that failed are not coming back
on a re-run.

The run does not stop at the scans. It stores and matches whatever travellers
have arrived since the last one, and joins each pending session to those now
covering it, because reconciliation runs off a match rather than a command of
its own (travellers.md `#acquisition`). One trigger therefore brings the whole
tree up to date, whichever half arrived first: a sheet scanned weeks before its
traveller is published is enriched by the run the traveller lands in front of.
"""

import argparse
import dataclasses
import enum
import hashlib
from collections.abc import Iterator, MutableSet, Sequence, Set
from pathlib import Path, PurePosixPath

from session_analysis import (
  assembly,
  extraction,
  issue_reporting,
  traveller_store,
)
from session_analysis.enums import IssueSeverity
from session_analysis.models import (
  Issue,
  Session,
  SheetFrame,
  SheetImage,
  Source,
)
from session_analysis.private_paths import PrivateTree, discover_private_tree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import (
  configuration,
  reconciliation,
  scan_decoding,
  session_keys,
  session_matching,
)
from session_analysis.unreviewed.rule_grid import SheetGeometryError
from session_analysis.unreviewed.sheet_structure import SheetStructureError
from session_analysis.vision_model_invocation import (
  DEFAULT_MODEL,
  CommandRunner,
  VisionModelInvocationError,
  run_claude,
)

# A sheet whose board count does not match its board-row count. One strip is cut
# per board row and the model is asked for one board per row strip, so the two
# counts are the same or the correspondence is broken — and it is positional, so
# a board dropped in the middle shifts every board after it onto the wrong row.
# High severity because nothing downstream can notice: the vote compares the two
# runs against each other, and both runs dropping the same strip is exactly the
# shape this takes.
_BOARD_COUNT_MISMATCH = issue_reporting.Failure(
  'board_count_mismatch', IssueSeverity.HIGH, 'sheet'
)

# A session whose footer named no key. It is stored and reviewable like any
# other, but nothing can match a traveller to it until a person supplies what
# the footer could not.
_UNNAMED_SESSION = issue_reporting.Failure(
  'unnamed_session', IssueSeverity.MEDIUM, 'footer'
)

_RECORD_SUFFIX = '.json'
# Appended rather than substituted, so a failed scan keeps its whole name and
# the sidecar sits next to it in a listing — as `capture_urls` does for a URL.
_FAILURE_SUFFIX = '.error'

# What one sheet can raise once the file has been decoded. Terminal for that
# sheet and harmless to the others, because each of them is a separate session:
# a container whose third page will not resolve still yields the first two,
# which have already been paid for by the time it fails.
#
# Terminal for the run rather than for the sheet, though. Both are raised
# against the model's reading of the layout rather than against the scan itself,
# and that reading varies between attempts: a sheet that raised
# `SheetGeometryError` here digitized on the next run, unchanged, its grid
# bounds landing where the first reading had put them half a row out. So a
# set-aside scan is worth one retry, and a cheap one — the layout reading
# precedes the two transcription calls, so a sheet that fails here pays for that
# reading alone.
#
# Retrying is left to a person moving the file back out of
# `scoresheets/failed/`, rather than done here: an automatic retry would spend
# again on every run, where a person can weigh whether this scan is worth
# another reading.
#
# `VisionModelInvocationError` is deliberately not among them. It says nothing
# about the sheet — it covers an auth failure and a rate limit as much as a
# request the model refuses every time — so a container is never archived
# because of one. `process_inbox` sets that container aside and stops the run,
# which is the treatment that survives being wrong about which it was: a passing
# outage, or a request the model will refuse every time. What that costs is the
# sheets of the container already read: they are given up rather than stored,
# because a record naming an archive path the container never reaches would be
# worse than re-reading it.
_TERMINAL_SHEET_ERRORS = (
  SheetGeometryError,
  SheetStructureError,
)


class SheetOutcome(enum.StrEnum):
  """What became of one sheet in a run."""

  DIGITIZED = 'digitized'
  # Recognized as already digitized, by content hash or by session key. The scan
  # still leaves the inbox — it is a scan of a session on hand, so the archive
  # is where it belongs.
  SKIPPED = 'skipped'
  FAILED = 'failed'
  # Never opened, because the run stopped at an earlier scan. Distinct from
  # `FAILED`: nothing is known against this scan at all, it is still in the
  # inbox rather than in `scoresheets/failed/`, and the next run reaches it with
  # no intervention.
  DEFERRED = 'deferred'


@dataclasses.dataclass(frozen=True)
class SheetReport:
  """One sheet's fate, in the terms the run summary prints."""

  # How the summary names it: the scan's filename, or that plus a page when the
  # file held several sheets. A label rather than a path — a container holding
  # three sheets is reported three times under one filename.
  sheet: str
  outcome: SheetOutcome
  # Why, in a phrase: the key it was digitized as, the record it duplicates, or
  # the error that stopped it.
  detail: str


def process_inbox(
  tree: PrivateTree,
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> issue_reporting.Read[Sequence[SheetReport]]:
  """Digitize every scan waiting in the inbox.

  Args:
    tree: the private tree whose inbox is read and whose archive, failure, and
      pending-record directories are written.
    model: the vision model to transcribe with.
    run_command: how the headless model invocation is run; injected so a test
      needs no model call.

  Returns:
    One report per sheet, in the order they were processed, alongside any
    run-level issue — a scan file holding several sheets reports each. A
    sheet's own findings live on the record it produced, not here; this says
    what happened to files, not what was hard to read.

  Raises:
    FileNotFoundError: if the inbox does not exist.
  """
  inbox = tree.scan_inbox
  if not inbox.is_dir():
    raise FileNotFoundError(f'no scan inbox at {inbox}')

  # Every key already spoken for, taken from the record filenames rather than
  # their contents: a record is named for its key, so the listing is the index
  # and no record has to be opened to build it.
  taken_keys = _stored_record_stems(tree)

  scans = list(_scans_in(inbox))
  reports: list[SheetReport] = []
  for index, scan in enumerate(scans):
    try:
      reports.extend(
        _process_scan(
          scan, tree, taken_keys, model=model, run_command=run_command
        )
      )
    except VisionModelInvocationError as error:
      # The model call failed, and this stage cannot tell the two reasons apart:
      # an outage that a later run would sail through, or this scan being one
      # the model refuses every time — a request too large, a reply that never
      # satisfied the schema. So the scan is given the treatment that survives
      # being wrong about which of the two it was.
      #
      # This scan is set aside, because leaving it would have every later run
      # meet it first and stop there: a scan that always fails would wedge the
      # inbox behind it for good, and nothing would say why. The sidecar says
      # what happened and moving the file back is the whole retry.
      #
      # What that costs, when it really was an outage, is one scan a run — so
      # re-triggering three times through one rate-limit window puts three
      # untried scans in `failed/` to be dragged back. Worth it against the
      # alternative: a bounded, visible, reversible cost rather than an inbox
      # that never moves again.
      #
      # The scans behind it are only deferred. They were never opened, so
      # nothing is known against them, and they cost nothing to leave — but they
      # are reported all the same, because a summary that simply stopped would
      # leave a person counting files to notice.
      _set_aside(
        scan,
        PurePosixPath(_archive_name(scan, _content_hash(scan))),
        tree,
        f'{type(error).__name__}: {error}',
      )
      reports.append(SheetReport(scan.name, SheetOutcome.FAILED, str(error)))
      reports.extend(
        SheetReport(
          later.name,
          SheetOutcome.DEFERRED,
          'the run stopped before this scan was read',
        )
        for later in scans[index + 1 :]
      )
      break
  return issue_reporting.Read(tuple(reports))


@dataclasses.dataclass(frozen=True)
class DigitizedSheet:
  """One sheet of a scan, read through to a named session."""

  page: int
  session: Session


@dataclasses.dataclass(frozen=True)
class UndigitizedSheet:
  """One sheet of a scan that could not be read, and why.

  `reason` does not name the page: the run summary's own label already does, and
  the sidecar — where the page is the whole point, since the file is what a
  person is handed — composes the two itself.
  """

  page: int
  reason: str


def digitize_scan(
  scan: Path,
  *,
  archived_as: PurePosixPath,
  content_hash: str,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> Sequence[DigitizedSheet | UndigitizedSheet]:
  """Read one scan file through extraction into named, validated `Session`s.

  The wiring that joins the rest of the pipeline: decode the file, transcribe
  each sheet twice, vote between the two reads, and name the result from its own
  footer. `archived_as` and `content_hash` are the provenance the vision model
  never sees — where the scan will live once the run finishes, and what
  identifies its bytes.

  One outcome per sheet, in page order: a scanner app writes one file per feed,
  so a container holding several sheets yields several sessions, each with its
  own footer and key. A sheet that cannot be read is reported in place rather
  than costing the whole file, because the sheets before it have already been
  transcribed and paying for them twice is the alternative.

  The reference date resolving a footer's year comes from the scan's own capture
  date, never today's: a scan reprocessed months later must resolve `6/29`
  against the day it was taken, or the year shifts silently.

  Raises:
    ScanDecodingError: the file could not be opened at all, so there are no
      pages to report on. A page that yields no image is reported as that
      page's own failure, leaving the rest of the container readable.
    VisionModelInvocationError: the model call failed. Not per-sheet, because it
      says nothing about any particular sheet — see `process_inbox`, which sets
      the container aside and stops the run. The sheets of it already read are
      given up with it: their records would name an archive path the container
      never reaches.
  """
  decoded = scan_decoding.decode_scan(scan)
  outcomes: list[DigitizedSheet | UndigitizedSheet] = []
  for read in decoded.value:
    if isinstance(read, scan_decoding.UndecodedPage):
      outcomes.append(UndigitizedSheet(read.page, read.reason))
      continue

    sheet = read
    try:
      transcription = extraction.transcribe_sheet(
        sheet.image, model=model, run_command=run_command
      )
    except _TERMINAL_SHEET_ERRORS as error:
      outcomes.append(
        UndigitizedSheet(sheet.page, f'{type(error).__name__}: {error}')
      )
      continue

    source = Source(
      image=SheetImage(
        path=str(archived_as),
        content_hash=content_hash,
        page=sheet.page,
        frame=SheetFrame(
          geometry=transcription.geometry,
          source_quad=transcription.source_quad,
        ),
      )
    )
    session = assembly.parse_and_assemble_voted_session(
      *transcription.raw_jsons,
      source,
      reference_date=sheet.captured_on,
    )
    outcomes.append(
      DigitizedSheet(
        sheet.page,
        _named(
          session,
          (
            *decoded.issues,
            *_counted(session, len(transcription.geometry.row_boxes)),
          ),
        ),
      )
    )
  return tuple(outcomes)


def _process_scan(
  scan: Path,
  tree: PrivateTree,
  taken_keys: MutableSet[str],
  *,
  model: str,
  run_command: CommandRunner,
) -> Sequence[SheetReport]:
  """Take one scan file as far as it goes, and move it out of the inbox.

  One report per sheet the file held, or a single report for the file when it
  never got as far as its sheets.
  """
  content_hash = _content_hash(scan)
  archived_as = PurePosixPath(_archive_name(scan, content_hash))
  archive = tree.scan_archive / archived_as

  # These exact bytes have been through a run before. Recognizing that here,
  # before extraction, is what makes re-dropping a file free.
  already_archived = _archived_scans(tree, content_hash)
  if already_archived:
    # Moved onto the copy already there rather than in beside it: the bytes are
    # identical by definition, so a second copy would differ only in the name
    # the file happened to arrive under.
    _move(scan, already_archived[0])
    return (
      SheetReport(
        scan.name,
        SheetOutcome.SKIPPED,
        f'the same scan is already archived as {already_archived[0].name}',
      ),
    )

  try:
    outcomes = digitize_scan(
      scan,
      archived_as=archived_as,
      content_hash=content_hash,
      model=model,
      run_command=run_command,
    )
  except scan_decoding.ScanDecodingError as error:
    # The file would not open at all, so there are no pages to report on. The
    # type is named in the sidecar as it is for a per-sheet failure, so a person
    # reading one can tell a file that would not open from a sheet whose grid
    # would not resolve.
    _set_aside(scan, archived_as, tree, f'{type(error).__name__}: {error}')
    return (SheetReport(scan.name, SheetOutcome.FAILED, str(error)),)

  digitized = [
    outcome for outcome in outcomes if isinstance(outcome, DigitizedSheet)
  ]
  # The page belongs in the sidecar even when the file held one sheet: what it
  # is read beside is the container, not the sheet.
  failures = [
    f'page {outcome.page}: {outcome.reason}'
    for outcome in outcomes
    if isinstance(outcome, UndigitizedSheet)
  ]
  if not digitized:
    _set_aside(scan, archived_as, tree, '\n'.join(failures))
    return tuple(
      SheetReport(
        _sheet_label(scan, outcome.page, outcomes),
        SheetOutcome.FAILED,
        outcome.reason,
      )
      for outcome in outcomes
      if isinstance(outcome, UndigitizedSheet)
    )

  reports: list[SheetReport] = []
  for outcome in outcomes:
    label = _sheet_label(scan, outcome.page, outcomes)
    if isinstance(outcome, UndigitizedSheet):
      reports.append(SheetReport(label, SheetOutcome.FAILED, outcome.reason))
      continue

    session = outcome.session
    stem = session_keys.record_stem(
      session.session_key, content_hash, outcome.page
    )
    if stem in taken_keys:
      # A key already taken means this sheet's session is on hand under
      # different bytes — a second photograph of a sheet already digitized. Two
      # sheets of one container never land here, because `record_stem` gives
      # each page after the first a suffix of its own.
      reports.append(
        SheetReport(
          label,
          SheetOutcome.SKIPPED,
          f'this session is already digitized as {stem}',
        )
      )
      continue

    record = tree.pending_session_records / f'{stem}{_RECORD_SUFFIX}'
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(session.model_dump_json(indent=2) + '\n')
    taken_keys.add(stem)
    reports.append(
      SheetReport(
        label,
        SheetOutcome.DIGITIZED,
        f'{stem} — {len(session.boards)} boards, '
        f'{len(session.issues)} session issues',
      )
    )

  _move(scan, archive)
  # A sidecar from an earlier attempt describes a scan that has now been read,
  # so it is deleted along with the failure it explained. Left behind, it would
  # sit in `failed/` naming a file no longer there.
  _forget_failure(tree, archived_as)
  if failures:
    # Beside the archived file rather than in `failed/`: the sheets that did
    # read name this path, so the file has to live here — but a re-run finds it
    # by content hash and never retries, so what failed is written down.
    archive.with_name(archive.name + _FAILURE_SUFFIX).write_text(
      '\n'.join(failures) + '\n'
    )
  return tuple(reports)


def _sheet_label(
  scan: Path, page: int, outcomes: Sequence[DigitizedSheet | UndigitizedSheet]
) -> str:
  """How one sheet is named in the run summary.

  The page is named only when the file held more than one, so the ordinary
  one-sheet scan reads as its own filename.
  """
  return scan.name if len(outcomes) == 1 else f'{scan.name} page {page}'


def _counted(session: Session, row_strips: int) -> tuple[Issue, ...]:
  """Whether the boards read back number the same as the row strips sent.

  One strip is cut per board row, and neither the printed header nor the footer
  is among them, so any difference means the model dropped or invented a board
  and every board after it is now against the wrong row.
  """
  if len(session.boards) == row_strips:
    return ()
  return (
    _BOARD_COUNT_MISMATCH.issue(
      f'{row_strips} board rows were sent as strips but '
      f'{len(session.boards)} boards came back, so which row each board '
      f'belongs to is no longer certain'
    ),
  )


def _named(session: Session, scan_issues: tuple[Issue, ...]) -> Session:
  """Give a session the key its footer names, and the scan's own findings.

  The key is derived here rather than in `assembly` because it is an ingest
  concern: assembly reads what the sheet says, and this decides what the session
  is then called.
  """
  session_key = session_keys.derive_session_key(session.event, session.date)
  issues = (*session.issues, *scan_issues)
  if not session_key:
    issues = (
      *issues,
      _UNNAMED_SESSION.issue(
        f'no session key follows from the footer (event {session.event!r}, '
        f'date {session.date}), so no traveller can be matched to this '
        f'session until review supplies one'
      ),
    )
  return session.model_copy(
    update={'session_key': session_key, 'issues': issues}
  )


def _scans_in(inbox: Path) -> Iterator[Path]:
  """Every file in the inbox that could be a scan.

  Leaves out anything whose name starts with a dot: `.DS_Store` rides along in a
  directory the Finder has been near, and a sync client parks its own
  bookkeeping there too. Neither is worth a failure report every run.

  Leaves out a failure sidecar too. Retrying a scan that was set aside means
  moving it back, and the sidecar sits beside it in `scoresheets/failed/` — so
  whoever drags one drags both, and the explanation should not then be read as a
  scan of its own.
  """
  return (
    path
    for path in sorted(inbox.iterdir())
    if path.is_file()
    and not path.name.startswith('.')
    and not path.name.endswith(_FAILURE_SUFFIX)
  )


def _content_hash(scan: Path) -> str:
  """The scan's content hash — the handle on its exact bytes."""
  return hashlib.sha256(scan.read_bytes()).hexdigest()


def _archive_name(scan: Path, content_hash: str) -> str:
  """What a scan is called once archived.

  Leads with the abbreviated content hash so a run can find an already-archived
  scan by its bytes without opening anything, and keeps the scanner's own name
  after it, which is often the only human-readable thing about a scan.

  A scan that already carries the prefix keeps the one it has. Retrying a
  set-aside scan means dragging it back from `scoresheets/failed/`, where it was
  filed under this same name, and prefixing it again on each attempt would grow
  the name a hash at a time.
  """
  prefix = session_keys.short_hash(content_hash)
  if scan.name.startswith(f'{prefix}-'):
    return scan.name
  return f'{prefix}-{scan.name}'


def _archived_scans(tree: PrivateTree, content_hash: str) -> Sequence[Path]:
  """Archived scans whose bytes hash to `content_hash`."""
  if not tree.scan_archive.is_dir():
    return ()
  prefix = session_keys.short_hash(content_hash)
  # The sidecar a partial failure leaves beside a scan shares its prefix, and is
  # not a scan. Returning it would have a re-dropped copy reported as already
  # archived under the sidecar's name, and then moved onto the sidecar itself.
  return sorted(
    path
    for path in tree.scan_archive.glob(f'{prefix}-*')
    if not path.name.endswith(_FAILURE_SUFFIX)
  )


def _stored_record_stems(tree: PrivateTree) -> MutableSet[str]:
  """Every session key already spoken for, pending or reviewed alike.

  Both are consulted: a sheet digitized months ago and long since reviewed is
  just as digitized as one still waiting, and re-photographing it should be
  recognized either way.
  """
  if not tree.session_records.is_dir():
    return set()
  return {
    record.stem for record in tree.session_records.rglob(f'*{_RECORD_SUFFIX}')
  }


def _move(scan: Path, destination: Path) -> None:
  """Move a scan out of the inbox.

  `replace` rather than a copy-and-delete: the inbox and its destination sit in
  one tree, so the move is atomic, and a destination that already exists holds
  bytes identical to these — every destination is named by the content hash, in
  the failure directory as much as the archive.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  scan.replace(destination)


def _forget_failure(tree: PrivateTree, named_as: PurePosixPath) -> None:
  """Remove the sidecar a previous run left for a scan now successfully read."""
  stale = tree.scan_failures / f'{named_as}{_FAILURE_SUFFIX}'
  stale.unlink(missing_ok=True)


def _set_aside(
  scan: Path, named_as: PurePosixPath, tree: PrivateTree, reason: str
) -> None:
  """Move a scan no sheet of which could be read, saying why beside it.

  Filed under the same content-hashed name the archive would have given it, so
  two scans that arrive under one filename — a scanner app that numbers nothing
  writes `Scan.pdf` every time — do not overwrite each other here. Losing a
  failed scan silently is the opposite of what this directory is for.
  """
  failed = tree.scan_failures / str(named_as)
  _move(scan, failed)
  sidecar = failed.with_name(failed.name + _FAILURE_SUFFIX)
  sidecar.write_text(reason + '\n')


def _plural(count: int) -> str:
  """The `s` a count of anything but one takes."""
  return '' if count == 1 else 's'


def summarize_run(reports: Sequence[SheetReport]) -> Iterator[str]:
  """The run summary, a line per report, aligned for reading down the column.

  An explicit trigger only beats a watcher if its output says what happened, so
  every sheet that was reached gets a line whatever became of it. A file that
  was never opened, or a run in which the model became unreachable partway
  through, gets a single line under the file's own name instead — there were no
  sheets to speak of.
  """
  if not reports:
    yield 'The inbox is empty.'
    return

  width = max(len(report.outcome) for report in reports)
  yield f'{len(reports)} sheet{_plural(len(reports))} from the inbox:'
  for report in reports:
    yield f'  {report.outcome:<{width}}  {report.sheet} — {report.detail}'


@dataclasses.dataclass(frozen=True)
class PendingSession:
  """A digitized session awaiting review, and the travellers covering it.

  `travellers` is empty for a session no capture matches, which is the ordinary
  state of one whose results have not been published yet. Such a session is
  carried anyway rather than left out, because the join has something to say
  about it too — see `reconcile_pending_sessions`.
  """

  # What the record is called in `pending/`, which is the handle on the file.
  stem: str
  session: Session
  travellers: tuple[Traveller, ...] = ()
  # Captures the record cites that are still stored yet that this run placed on
  # no session — an ambiguous date, or a stored record that no longer parses.
  # They tell a capture that could not be placed from one that was withdrawn,
  # which is what decides whether the enrichment stands, and they are what the
  # run names when it says why a session was held.
  unplaced_captures: tuple[str, ...] = ()
  # Captures the record cites whose files are gone. Withdrawing a capture is
  # deleting it, so these are what a record loses its enrichment over — and
  # naming them is the difference between a run that says the enrichment went
  # and one that says what took it.
  withdrawn_captures: tuple[str, ...] = ()


class SessionOutcome(enum.StrEnum):
  """What became of one pending session in a reconciliation pass."""

  # The join rewrote the record — enriched it from the travellers now covering
  # it, or took the enrichment back off where nothing covers it any more.
  RECONCILED = 'reconciled'
  # Left exactly as it stands, because a capture the record cites could not be
  # placed. Joining without it would take its enrichment off over a fault the
  # run has already reported, so the record waits for a person instead.
  HELD = 'held'


@dataclasses.dataclass(frozen=True)
class ReconcileReport:
  """One session's fate in a reconciliation pass."""

  session: str
  outcome: SessionOutcome
  # Why, in a phrase: what the join enriched the record from, what it took back
  # off, or the capture it could not place.
  detail: str
  # What the join said about the record as a whole that it had not said before —
  # above all a capture naming us in no row, which is the shape a capture
  # matched to the wrong session takes. Board-level findings stay on the record
  # for review; these are the ones worth a person's attention at the console.
  issues: tuple[Issue, ...] = ()


def match_pending_sessions(
  tree: PrivateTree,
) -> issue_reporting.Read[Sequence[PendingSession]]:
  """Store any newly saved captures and match them to pending sessions.

  Storing runs alongside the inbox rather than under a command of its own
  because a capture saved by hand is the acquisition fallback (travellers.md
  `#acquisition`), and a fallback nothing picks up is not one. One explicit
  trigger brings the whole tree up to date, which is also why there is no
  separate reconcile command.

  Returns:
    Every pending session, each carrying the travellers matched to it, in a
    stable order by record name — alongside every issue the storing, reading,
    and matching raised. A tree with no captures yet is an ordinary answer
    rather than an error: the scans and the captures arrive by unrelated
    routes, and either can come first.
  """
  issues: list[Issue] = []
  if tree.traveller_captures.is_dir():
    stored = traveller_store.store_travellers(tree)
    issues.extend(stored.issues)

  records = session_matching.read_stored_travellers(tree)
  # A record whose capture is gone is not a traveller this run has. The capture
  # is the durable half and the record only what was derived from it, so
  # withdrawing a capture is deleting the file — and a record outliving one
  # would keep enriching the session the capture was taken off.
  #
  # A capture root that is missing altogether therefore reads as every capture
  # withdrawn, and one run takes the enrichment off every pending session. That
  # is the limit case of the same gesture rather than a separate hazard, and the
  # private tree is a git checkout, so the records a wrong run rewrites are
  # recoverable from its history.
  travellers = tuple(
    traveller
    for traveller in records.value
    if (tree.traveller_captures / traveller.reference.path).is_file()
  )
  sessions = session_matching.read_pending_sessions(tree)
  matched = session_matching.match_travellers(travellers, sessions.value)
  issues.extend((*records.issues, *sessions.issues, *matched.issues))

  # Matching answers "which session is this capture's?", and the join asks the
  # opposite — "which captures cover this session?" — so the mapping is turned
  # around here, once, rather than by each reader of it.
  covering: dict[str, list[Traveller]] = {}
  for traveller in travellers:
    stem = matched.value.get(traveller.reference.path)
    if stem:
      covering.setdefault(stem, []).append(traveller)

  sessions_by_stem = {
    session_matching.stem_of(session): session for session in sessions.value
  }
  pending = tuple(
    _pending_session(
      stem,
      sessions_by_stem[stem],
      covering.get(stem, ()),
      matched.value.keys(),
      tree.traveller_captures,
    )
    for stem in sorted(sessions_by_stem)
  )
  return issue_reporting.Read(pending, tuple(issues))


def _pending_session(
  stem: str,
  session: Session,
  covering: Sequence[Traveller],
  placed: Set[str],
  captures: Path,
) -> PendingSession:
  """One pending session, as a run's matching left it.

  Args:
    stem: what the record is called in `pending/`.
    session: the record as it stands, before any join this run makes.
    covering: the travellers this run placed on it, in any order.
    placed: every capture path this run placed on some session.
    captures: the capture root, which tells a capture still on disk from one
      that has been withdrawn.
  """
  # What became of each capture the record cites. Read off the file rather than
  # off the travellers that were parsed, because a capture whose stored record
  # no longer parses is dropped before matching sees it — it would look placed
  # nowhere and withdrawn at once.
  unplaced = []
  withdrawn = []
  for reference in session.source.travellers:
    if not (captures / reference.path).is_file():
      withdrawn.append(reference.path)
    elif reference.path not in placed:
      unplaced.append(reference.path)

  return PendingSession(
    stem,
    session,
    # Sorted, so a record the join rewrites cites its captures in the same order
    # every run and a re-run compares equal to what the last one wrote.
    travellers=tuple(
      sorted(covering, key=lambda traveller: traveller.reference.path)
    ),
    unplaced_captures=tuple(unplaced),
    withdrawn_captures=tuple(withdrawn),
  )


def reconcile_pending_sessions(
  tree: PrivateTree,
  pending: Sequence[PendingSession],
  *,
  our_name: str,
) -> Sequence[ReconcileReport]:
  """Join each pending session to its travellers, rewriting what changed.

  This is what makes a traveller landing trigger reconciliation rather than wait
  for a command of its own (travellers.md `#acquisition`). The record stays in
  `pending/` either way: the join enriches a session, and it is review that
  graduates one (travellers.md `#timing`).

  Every pending session is joined, not only the newly matched ones. A session
  whose capture has since been withdrawn has to give its enrichment back, or the
  record would keep asserting a deal that nothing now supports — and a run with
  no travellers is the only thing that does that. A session citing a capture
  this run could not place is passed over instead: nothing was withdrawn from
  it, and rejoining over what is left would drop that capture's enrichment as
  surely as a withdrawal would. Rewriting is confined to records the join
  actually changed, so the common re-run, over travellers that have not moved,
  touches no file and reports nothing.

  Args:
    tree: the private tree whose pending records are rewritten in place.
    pending: every pending session and the travellers covering it.
    our_name: the configured player name, used to find our row.

  Returns:
    One report per session the join rewrote or held back, in the order they
    were given. A session it found nothing to do for is absent.
  """
  reports: list[ReconcileReport] = []
  for pending_session in pending:
    # A record citing a capture that is still stored but that this run could not
    # place lost it to a fault the run has already reported — an ambiguous date,
    # or a stored record that no longer parses. Rejoining without it would take
    # its enrichment and its citation off the record, destroying work nobody
    # withdrew; that holds whether or not the run placed some other capture on
    # the same session, so the record is left exactly as it stands.
    #
    # Reported rather than passed over quietly: the record is frozen until a
    # person resolves what the run could not, and every run until then would
    # otherwise print the same line a healthy tree does.
    if pending_session.unplaced_captures:
      reports.append(
        ReconcileReport(
          pending_session.stem,
          SessionOutcome.HELD,
          _held_detail(pending_session.unplaced_captures),
        )
      )
      continue

    joined = reconciliation.reconcile_session(
      pending_session.session, pending_session.travellers, our_name=our_name
    )
    # Compared as records rather than as serialized text, so a difference in
    # formatting alone never counts as a change worth a rewrite.
    if joined == pending_session.session:
      continue

    record = (
      tree.pending_session_records / f'{pending_session.stem}{_RECORD_SUFFIX}'
    )
    record.write_text(joined.model_dump_json(indent=2) + '\n')
    # Only what this join added: a finding the record already carried was
    # reported by the run that first wrote it.
    raised = tuple(
      issue
      for issue in joined.issues
      if issue not in pending_session.session.issues
    )
    reports.append(
      ReconcileReport(
        pending_session.stem,
        SessionOutcome.RECONCILED,
        _reconciled_detail(pending_session, joined),
        raised,
      )
    )
  return tuple(reports)


def _held_detail(unplaced: Sequence[str]) -> str:
  """Why a session was left as it stands, in the terms the summary prints.

  Names the captures rather than counting them: what the reader has to go and do
  is resolve those files, and a count would send them looking for which.
  """
  return (
    f'cites {", ".join(unplaced)}, which this run could not place — resolve '
    f'that and the join picks the session up again'
  )


def _reconciled_detail(pending: PendingSession, joined: Session) -> str:
  """What a rewritten record now holds, in the terms the summary prints."""
  if not pending.travellers:
    gone = pending.withdrawn_captures
    if not gone:
      # Nothing vanished, so a capture the record cited was placed on some other
      # session this run — the match moved rather than the file.
      return 'no traveller covers it now, so its enrichment was taken back off'

    # Named rather than counted: on a whole capture root gone missing this is
    # the only thing separating an accident from a deliberate withdrawal, and
    # the reader needs the filename either way.
    is_gone = 'is' if len(gone) == 1 else 'are'
    return (
      f"{', '.join(gone)} {is_gone} no longer stored, so the record's "
      f'enrichment was taken back off'
    )

  enriched = sum(1 for board in joined.boards if board.deal)
  return (
    f'enriched from {len(pending.travellers)} '
    f'traveller{_plural(len(pending.travellers))} — '
    f'{enriched} of {len(joined.boards)} boards have a deal'
  )


def summarize_reconciliation(
  reports: Sequence[ReconcileReport],
) -> Iterator[str]:
  """The reconciliation summary, a line per session the join reports.

  A session the join found nothing to do for says nothing: once a session is
  reconciled that is what every later run finds, and printing the whole of
  `pending/` each time would bury the sessions worth reading. A session held
  back does get a line, because it is frozen until a person resolves what the
  run could not — and silence there reads as the "nothing to do" a healthy run
  prints.

  What the join raised against a whole record is printed under it: a record
  enriched from the wrong session's capture is otherwise indistinguishable here
  from one enriched from the right one.
  """
  if not reports:
    yield 'Every pending session is up to date.'
    return

  width = max(len(report.outcome) for report in reports)
  yield f'{len(reports)} session{_plural(len(reports))} the join reports:'
  for report in reports:
    yield f'  {report.outcome:<{width}}  {report.session} — {report.detail}'
    for issue in report.issues:
      yield f'    {issue.code}: {issue.message}'


def main() -> None:
  """Digitize the inbox, then reconcile what the travellers now cover."""
  _parse_args()
  tree = discover_private_tree()

  # Read before the inbox, so a tree with no configuration yet costs no model
  # call: a run that transcribed a sheet and then stopped for want of a name
  # would have spent the expensive part to do half the job.
  try:
    settings = configuration.load_configuration(tree)
  except configuration.ConfigurationError as error:
    raise SystemExit(str(error)) from error

  run = process_inbox(tree)
  for line in summarize_run(run.value):
    print(line)
  _print_issues(run.issues)

  pending = match_pending_sessions(tree)
  matched = sum(
    len(pending_session.travellers) for pending_session in pending.value
  )
  print()
  print(f'{matched} capture{_plural(matched)} matched to a digitized session.')
  for pending_session in pending.value:
    for traveller in pending_session.travellers:
      print(f'  {traveller.reference.path} — {pending_session.stem}')
  _print_issues(pending.issues)

  reconciled = reconcile_pending_sessions(
    tree, pending.value, our_name=settings.player_name
  )
  print()
  for line in summarize_reconciliation(reconciled):
    print(line)


def _print_issues(issues: Sequence[Issue]) -> None:
  """Print whatever a run could not do, indented under what it did."""
  for issue in issues:
    print(f'  {issue.code}: {issue.message}')


def _parse_args() -> argparse.Namespace:
  """Parse the command line, which takes no arguments of its own.

  The private tree is found rather than configured (private_paths), so there is
  nothing to pass — but a parser still earns its place: it gives the command a
  `--help` describing itself, and turns a mistyped flag into a complaint rather
  than a silently ordinary run.
  """
  parser = argparse.ArgumentParser(
    description='Digitize the scans waiting in the scoresheet inbox, and '
    'reconcile the sessions their travellers now cover.'
  )
  return parser.parse_args()


if __name__ == '__main__':
  main()
