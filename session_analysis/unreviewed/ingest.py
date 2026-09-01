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
than given a disambiguating suffix.

A scan that raises moves to `scoresheets/failed/` with a sidecar naming what
went wrong. Terminal rather than staging: leaving it in the inbox would re-spend
a model call every run, and a directory of files with no explanation beside them
is not the loud failure this stage is supposed to produce.
"""

import argparse
import dataclasses
import enum
import hashlib
from collections.abc import Iterator, Mapping, MutableSet, Sequence
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
from session_analysis.rule_grid import SheetGeometryError
from session_analysis.unreviewed import (
  scan_decoding,
  session_keys,
  session_matching,
)
from session_analysis.vision_model_invocation import (
  DEFAULT_MODEL,
  CommandRunner,
  VisionModelInvocationError,
  run_claude,
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

# What a scan can raise on its way to a record. Each is terminal for that scan
# and harmless to the rest of the run, so they are caught together and the scan
# is set aside with the message as its explanation.
_TERMINAL_SCAN_ERRORS = (
  scan_decoding.ScanDecodingError,
  SheetGeometryError,
  VisionModelInvocationError,
)


class ScanOutcome(enum.StrEnum):
  """What became of one scan in a run."""

  DIGITIZED = 'digitized'
  # Recognized as already digitized, by content hash or by session key. The scan
  # still leaves the inbox — it is a scan of a session on hand, so the archive
  # is where it belongs.
  SKIPPED = 'skipped'
  FAILED = 'failed'


@dataclasses.dataclass(frozen=True)
class ScanReport:
  """One scan's fate, in the terms the run summary prints."""

  scan: str
  outcome: ScanOutcome
  # Why, in a phrase: the key it was digitized as, the record it duplicates, or
  # the error that stopped it.
  detail: str


def process_inbox(
  tree: PrivateTree,
  *,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> issue_reporting.Read[Sequence[ScanReport]]:
  """Digitize every scan waiting in the inbox.

  Args:
    tree: the private tree whose inbox is read and whose archive, failure, and
      pending-record directories are written.
    model: the vision model to transcribe with.
    run_command: how the headless model invocation is run; injected so a test
      needs no model call.

  Returns:
    One report per scan, in the order they were processed, alongside any
    run-level issue. A scan's own findings live on the record it produced, not
    here — this says what happened to files, not what was hard to read.

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

  reports = []
  for scan in _scans_in(inbox):
    report = _process_scan(
      scan, tree, taken_keys, model=model, run_command=run_command
    )
    reports.append(report)
  return issue_reporting.Read(tuple(reports))


def digitize_scan(
  scan: Path,
  *,
  archived_as: PurePosixPath,
  content_hash: str,
  model: str = DEFAULT_MODEL,
  run_command: CommandRunner = run_claude,
) -> Session:
  """Read one scan file through extraction into a named, validated `Session`.

  The wiring the rest of the pipeline was built to be joined by: decode the
  file, transcribe it twice, vote between the two reads, and name the result
  from its own footer. `archived_as` and `content_hash` are the provenance the
  vision model never sees — where the scan will live once the run finishes, and
  what identifies its bytes.

  The reference date resolving the footer's year comes from the scan's own
  capture date, never today's: a scan reprocessed months later must resolve
  `6/29` against the day it was taken, or the year shifts silently.

  Raises:
    ScanDecodingError: the file yielded no image to transcribe.
    SheetGeometryError: the scan's grid could not be resolved.
    VisionModelInvocationError: a headless model invocation failed.
  """
  decoded = scan_decoding.decode_scan(scan)
  transcription = extraction.transcribe_sheet(
    decoded.value.image, model=model, run_command=run_command
  )
  source = Source(
    image=SheetImage(
      path=str(archived_as),
      content_hash=content_hash,
      frame=SheetFrame(
        geometry=transcription.geometry,
        source_quad=transcription.source_quad,
      ),
    )
  )
  session = assembly.parse_and_assemble_voted_session(
    *transcription.raw_jsons,
    source,
    reference_date=decoded.value.captured_on,
  )
  return _named(session, decoded.issues)


def _process_scan(
  scan: Path,
  tree: PrivateTree,
  taken_keys: MutableSet[str],
  *,
  model: str,
  run_command: CommandRunner,
) -> ScanReport:
  """Take one scan as far as it goes, and move it out of the inbox."""
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
    return ScanReport(
      scan.name,
      ScanOutcome.SKIPPED,
      f'the same scan is already archived as {already_archived[0].name}',
    )

  try:
    session = digitize_scan(
      scan,
      archived_as=archived_as,
      content_hash=content_hash,
      model=model,
      run_command=run_command,
    )
  except _TERMINAL_SCAN_ERRORS as error:
    _set_aside(scan, tree, error)
    return ScanReport(scan.name, ScanOutcome.FAILED, str(error))

  stem = session_keys.record_stem(session.session_key, content_hash)
  # A key already taken means this sheet's session is on hand under different
  # bytes — a second photograph of a sheet already digitized. An unnamed record
  # leads with its own content hash, so it never lands here spuriously.
  if stem in taken_keys:
    _move(scan, archive)
    return ScanReport(
      scan.name,
      ScanOutcome.SKIPPED,
      f'this session is already digitized as {stem}',
    )

  record = tree.pending_session_records / f'{stem}{_RECORD_SUFFIX}'
  record.parent.mkdir(parents=True, exist_ok=True)
  record.write_text(session.model_dump_json(indent=2) + '\n')
  taken_keys.add(stem)
  _move(scan, archive)

  return ScanReport(
    scan.name,
    ScanOutcome.DIGITIZED,
    f'{stem} — {len(session.boards)} boards, '
    f'{len(session.issues)} session issues',
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
  """
  return (
    path
    for path in sorted(inbox.iterdir())
    if path.is_file() and not path.name.startswith('.')
  )


def _content_hash(scan: Path) -> str:
  """The scan's content hash — the handle on its exact bytes."""
  return hashlib.sha256(scan.read_bytes()).hexdigest()


def _archive_name(scan: Path, content_hash: str) -> str:
  """What a scan is called once archived.

  Leads with the abbreviated content hash so a run can find an already-archived
  scan by its bytes without opening anything, and keeps the scanner's own name
  after it, which is often the only human-readable thing about a scan.
  """
  return f'{session_keys.short_hash(content_hash)}-{scan.name}'


def _archived_scans(tree: PrivateTree, content_hash: str) -> Sequence[Path]:
  """Archived scans whose bytes hash to `content_hash`."""
  if not tree.scan_archive.is_dir():
    return ()
  prefix = session_keys.short_hash(content_hash)
  return sorted(tree.scan_archive.glob(f'{prefix}-*'))


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
  bytes identical to these — it is only ever reached by way of the content hash
  that named it.
  """
  destination.parent.mkdir(parents=True, exist_ok=True)
  scan.replace(destination)


def _set_aside(scan: Path, tree: PrivateTree, error: Exception) -> None:
  """Move a scan that raised somewhere terminal, saying why beside it."""
  failed = tree.scan_failures / scan.name
  _move(scan, failed)
  sidecar = failed.with_name(failed.name + _FAILURE_SUFFIX)
  sidecar.write_text(f'{type(error).__name__}: {error}\n')


def summarize_run(reports: Sequence[ScanReport]) -> Iterator[str]:
  """The run summary, a line per scan, aligned for reading down the column.

  An explicit trigger only beats a watcher if its output says what happened, so
  every scan gets a line whatever became of it.
  """
  if not reports:
    yield 'The inbox is empty.'
    return

  width = max(len(report.outcome) for report in reports)
  plural = '' if len(reports) == 1 else 's'
  yield f'{len(reports)} scan{plural} in the inbox:'
  for report in reports:
    yield f'  {report.outcome:<{width}}  {report.scan} — {report.detail}'


def match_new_captures(
  tree: PrivateTree,
) -> issue_reporting.Read[Mapping[str, str]]:
  """Store any newly saved captures and match them to pending sessions.

  Storing runs alongside the inbox rather than under a command of its own
  because a capture saved by hand is the acquisition fallback (travellers.md
  `#acquisition`), and a fallback nothing picks up is not one. One explicit
  trigger brings the whole tree up to date, which is also why there is no
  separate reconcile command.

  Returns:
    The session each traveller belongs to, keyed by capture path, alongside
    every issue the storing, reading, and matching raised. A tree with no
    captures yet is an ordinary empty answer rather than an error — the scans
    and the captures arrive by unrelated routes, and either can come first.
  """
  issues: list[Issue] = []
  if tree.traveller_captures.is_dir():
    stored = traveller_store.store_travellers(tree)
    issues.extend(stored.issues)

  travellers = session_matching.read_stored_travellers(tree)
  sessions = session_matching.read_pending_sessions(tree)
  matched = session_matching.match_travellers(travellers.value, sessions.value)
  issues.extend((*travellers.issues, *sessions.issues, *matched.issues))
  return issue_reporting.Read(matched.value, tuple(issues))


def main() -> None:
  """Process the scan inbox and report what happened to each scan."""
  _parse_args()
  tree = discover_private_tree()

  run = process_inbox(tree)
  for line in summarize_run(run.value):
    print(line)
  _print_issues(run.issues)

  captures = match_new_captures(tree)
  print()
  print(f'{len(captures.value)} captures matched to a digitized session.')
  for capture, stem in sorted(captures.value.items()):
    print(f'  {capture} — {stem}')
  _print_issues(captures.issues)


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
    description='Digitize the scans waiting in the scoresheet inbox.'
  )
  return parser.parse_args()


if __name__ == '__main__':
  main()
