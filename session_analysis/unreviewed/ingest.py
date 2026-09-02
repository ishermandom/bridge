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
from session_analysis.rule_grid import SheetGeometryError
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import (
  configuration,
  reconciliation,
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


def _plural(count: int) -> str:
  """The `s` a count of anything but one takes."""
  return '' if count == 1 else 's'


def summarize_run(reports: Sequence[ScanReport]) -> Iterator[str]:
  """The run summary, a line per scan, aligned for reading down the column.

  An explicit trigger only beats a watcher if its output says what happened, so
  every scan gets a line whatever became of it.
  """
  if not reports:
    yield 'The inbox is empty.'
    return

  width = max(len(report.outcome) for report in reports)
  yield f'{len(reports)} scan{_plural(len(reports))} in the inbox:'
  for report in reports:
    yield f'  {report.outcome:<{width}}  {report.scan} — {report.detail}'


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
  for one in pending:
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
    if one.unplaced_captures:
      reports.append(
        ReconcileReport(
          one.stem, SessionOutcome.HELD, _held_detail(one.unplaced_captures)
        )
      )
      continue

    joined = reconciliation.reconcile_session(
      one.session, one.travellers, our_name=our_name
    )
    # Compared as records rather than as serialized text, so a difference in
    # formatting alone never counts as a change worth a rewrite.
    if joined == one.session:
      continue

    record = tree.pending_session_records / f'{one.stem}{_RECORD_SUFFIX}'
    record.write_text(joined.model_dump_json(indent=2) + '\n')
    # Only what this join added: a finding the record already carried was
    # reported by the run that first wrote it.
    raised = tuple(
      issue for issue in joined.issues if issue not in one.session.issues
    )
    reports.append(
      ReconcileReport(
        one.stem,
        SessionOutcome.RECONCILED,
        _reconciled_detail(one, joined),
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
  matched = sum(len(one.travellers) for one in pending.value)
  print()
  print(f'{matched} capture{_plural(matched)} matched to a digitized session.')
  for one in pending.value:
    for traveller in one.travellers:
      print(f'  {traveller.reference.path} — {one.stem}')
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
