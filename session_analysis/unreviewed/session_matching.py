# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Deciding which digitized session a captured traveller belongs to.

A traveller and a sheet reach the pipeline by unrelated routes and at unrelated
times — a capture is fetched or saved by hand, sometimes days after the session,
sometimes before its sheet is ever scanned. Something has to pair them up before
reconciliation can join them, and that is this module.

The pairing reads the capture's own parsed metadata, never its filename or URL:
the club's directors each file under their own naming and an ACBL URL is an
opaque game id, so neither handle says which session it holds (travellers.md
`#acquisition`).

What it matches on is the date alone, and that is worth being explicit about,
because the tracker and travellers.md both once expected event and date
together. One session's event name is spelled differently by every source that
publishes it — `John & Will's Monday Bridge`, `Palo Alto Duplicate`, and the
club's own `Monday Pairs` are one game — so an event comparison between a
capture and a sheet rejects true matches far more often than it catches false
ones. The date is what every source states and states alike.

Date alone is ambiguous only on a day two sessions were played, which is real
but uncommon. Rather than guess, an ambiguous capture is reported and matched to
neither; tasks.md `#multi-session-days` carries the work to resolve it.
"""

import datetime
from collections.abc import Mapping, Sequence
from pathlib import Path

from session_analysis import issue_reporting
from session_analysis.enums import IssueSeverity
from session_analysis.models import Session
from session_analysis.private_paths import PrivateTree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import session_keys

# Two sessions on one date, and a capture that states only a date: which one it
# belongs to cannot be told, so it is left for a person rather than guessed.
_AMBIGUOUS_SESSION_MATCH = issue_reporting.Failure(
  'ambiguous_session_match', IssueSeverity.MEDIUM, 'capture'
)
# A capture stating no date of its own can be matched to nothing, since the date
# is the whole of the join.
_UNDATED_CAPTURE = issue_reporting.Failure(
  'undated_capture', IssueSeverity.MEDIUM, 'capture'
)
# A stored record that no longer validates — most likely written under an older
# shape of the model. Worth a person's attention: whatever it holds is invisible
# to matching until it is re-derived or removed.
_UNREADABLE_RECORD = issue_reporting.Failure(
  'unreadable_record', IssueSeverity.MEDIUM, 'record'
)

_RECORD_SUFFIX = '.json'


def match_travellers(
  travellers: Sequence[Traveller], sessions: Sequence[Session]
) -> issue_reporting.Read[Mapping[str, str]]:
  """Pair each traveller with the session it records, where one is clear.

  Args:
    travellers: the stored travellers to place, in any order.
    sessions: the digitized sessions they might belong to.

  Returns:
    The session each traveller belongs to, keyed by the traveller's capture
    path and valued by the session record's filename stem — both durable
    handles on disk. A traveller no session matches is simply absent, with no
    issue: a capture routinely arrives before its sheet is scanned, and saying
    so every run would bury the reports that matter. A traveller matching more
    than one session is absent too, but reported.
  """
  sessions_by_date: dict[datetime.date, list[Session]] = {}
  for session in sessions:
    # A session whose footer date could not be read is unmatchable, and already
    # carries the issue saying so from `parse_footer` — repeating it here would
    # report one unreadable footer twice.
    if session.date:
      sessions_by_date.setdefault(session.date, []).append(session)

  matches: dict[str, str] = {}
  issues = []
  for traveller in travellers:
    if not traveller.date:
      issues.append(
        _UNDATED_CAPTURE.issue(
          f'{traveller.reference.path} states no date, so it cannot be '
          f'matched to a session: {traveller.event!r}'
        )
      )
      continue

    candidates = sessions_by_date.get(traveller.date, ())
    if len(candidates) == 1:
      matches[traveller.reference.path] = stem_of(candidates[0])
    elif len(candidates) > 1:
      issues.append(
        _AMBIGUOUS_SESSION_MATCH.issue(
          f'{traveller.reference.path} is dated {traveller.date}, which '
          f'{len(candidates)} digitized sessions share '
          f'({", ".join(sorted(stem_of(one) for one in candidates))}); '
          f'assign it by hand'
        )
      )

  return issue_reporting.Read(matches, tuple(issues))


def read_stored_travellers(
  tree: PrivateTree,
) -> issue_reporting.Read[Sequence[Traveller]]:
  """Read every stored traveller record under `tree`.

  A record that no longer parses is reported and skipped rather than raising:
  one stale file left over from an older shape should not stop a run over the
  rest. The records root not existing at all is not an error either — it simply
  means no capture has been stored yet.
  """
  return _read_records(tree.traveller_records, Traveller, 'traveller')


def read_pending_sessions(
  tree: PrivateTree,
) -> issue_reporting.Read[Sequence[Session]]:
  """Read every digitized session still awaiting reconciliation and review."""
  return _read_records(tree.pending_session_records, Session, 'session')


def stem_of(session: Session) -> str:
  """The filename a session's pending record is stored under.

  Public because a match is only useful to a caller that can then find the
  record: `match_travellers` values its answer by this stem, so reading that
  answer means deriving the same stem for the sessions it names.
  """
  return session_keys.record_stem(
    session.session_key, session.source.image.content_hash
  )


def _read_records[RecordT: (Traveller, Session)](
  root: Path, record_type: type[RecordT], description: str
) -> issue_reporting.Read[Sequence[RecordT]]:
  """Read and validate every JSON record beneath a root directory."""
  if not root.is_dir():
    return issue_reporting.Read(())

  records = []
  issues = []
  for path in sorted(root.rglob(f'*{_RECORD_SUFFIX}')):
    try:
      records.append(record_type.model_validate_json(path.read_text()))
    except ValueError as error:
      issues.append(
        _UNREADABLE_RECORD.issue(
          f'could not read {path} as a {description} record, so it took no '
          f'part in matching: {error}'
        )
      )
  return issue_reporting.Read(tuple(records), tuple(issues))
