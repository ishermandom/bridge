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

A capture is placed by its date, never by its event name. One session's event
name is spelled differently by every source that publishes it: `John & Will's
Monday Bridge`, `Palo Alto Duplicate`, and the club's own `Monday Pairs` are one
game. So an event comparison between a capture and a sheet rejects true matches
far more often than it catches false ones. The date is what every source states
and states alike.

A date can hold more than one game, though — two club games published for one
day, or two sessions of ours. So the sessions sharing a capture's date are
narrowed by their opening leads. Each lead a sheet records must be a card that
the capture's deal gives the hand on lead, and a capture whose deals fail too
many of a sheet's leads is a capture of another game. travellers.md `#matching`
covers why the leads are read rather than our name in the rows.

What survives the narrowing decides the match. If one session survives, the
capture matches it. If none does, the capture is ruled out as the other game
played that day. If several do, the capture is reported rather than guessed at,
since nothing in it tells those sessions apart; tasks.md `#multi-session-days`
carries what is left of that case.
"""

import dataclasses
import datetime
import fractions
from collections.abc import Mapping, Sequence
from pathlib import Path

from session_analysis import issue_reporting
from session_analysis.enums import IssueSeverity
from session_analysis.models import PlayedContract, Session
from session_analysis.private_paths import PrivateTree
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import deal_checks, session_keys

# A capture whose deals fit several sessions of its date equally well: nothing
# says which session it belongs to, so it is left for a person to assign rather
# than guessed at.
_AMBIGUOUS_SESSION_MATCH = issue_reporting.Failure(
  'ambiguous_session_match', IssueSeverity.MEDIUM, 'capture'
)
# A capture stating no date of its own can be matched to nothing, since the date
# is the whole of the join.
_UNDATED_CAPTURE = issue_reporting.Failure(
  'undated_capture', IssueSeverity.MEDIUM, 'capture'
)
# A session that no capture covers although captures of its date are stored: its
# opening leads ruled out every one of them. A sheet misread badly enough to
# rule out its own game's capture leaves exactly this shape, so this issue ranks
# high; travellers.md `#matching` covers why the session is what gets reported.
_NO_CAPTURE_OF_DATE_FITS = issue_reporting.Failure(
  'no_capture_of_date_fits', IssueSeverity.HIGH, 'session'
)
# A session with no capture of its date stored. Most often its results are not
# fetched yet, which is the ordinary state of a fresh sheet, so this issue ranks
# low.
_NO_CAPTURE_OF_DATE_STORED = issue_reporting.Failure(
  'no_capture_of_date_stored', IssueSeverity.LOW, 'session'
)
# A stored record that no longer validates — most likely written under an older
# shape of the model. Worth a person's attention: whatever it holds is invisible
# to matching until it is re-derived or removed.
_UNREADABLE_RECORD = issue_reporting.Failure(
  'unreadable_record', IssueSeverity.MEDIUM, 'record'
)

_RECORD_SUFFIX = '.json'

# The share of a sheet's opening leads that a capture's deals may fail with the
# capture still counted as that sheet's game. A card led in one game sits in the
# same seat's hand in another game's deal only about one time in four, so
# another game's capture fails around three leads in four, while the sheet's own
# game fails only where the sheet was misread. One third sits well clear of
# both.
_TOLERATED_IMPOSSIBLE_LEAD_SHARE = fractions.Fraction(1, 3)


@dataclasses.dataclass(frozen=True)
class Matches:
  """What matching settled about the captures it was given.

  A capture in neither field is one that matching reached no verdict on: no
  session shares its date, it states no date, or it fits several sessions
  equally well.
  """

  # The session each matched capture belongs to, keyed by the capture's path and
  # valued by the session record's filename stem — both durable handles on disk.
  sessions: Mapping[str, str]
  # Captures whose deals cannot support the opening leads of any session sharing
  # their date — most likely the other game played that day. A verdict rather
  # than a fault, so none carries an issue; a session left with no capture is
  # reported instead, and travellers.md `#matching` covers why.
  ruled_out: frozenset[str]


def match_travellers(
  travellers: Sequence[Traveller], sessions: Sequence[Session]
) -> issue_reporting.Read[Matches]:
  """Pair each traveller with the session it records, where one is clear.

  Args:
    travellers: the stored travellers to place, in any order.
    sessions: the digitized sessions they might belong to.

  Returns:
    A `Matches`: which session each traveller belongs to, and which travellers
    every session sharing their date ruled out. A traveller that no session
    shares a date with is in neither field and raises no issue: a capture
    routinely arrives before its sheet is scanned, and saying so every run would
    bury the reports that matter. A traveller that fits several sessions equally
    well is in neither field either, but is reported.

    Every dated session left with no capture is reported too: at high severity
    where captures of its date are stored and none fits it, and at low severity
    where none is stored yet.
  """
  sessions_by_date: dict[datetime.date, list[Session]] = {}
  for session in sessions:
    # A session whose footer date could not be read is unmatchable, and already
    # carries the issue saying so from `parse_footer` — repeating it here would
    # report one unreadable footer twice.
    if session.date:
      sessions_by_date.setdefault(session.date, []).append(session)

  matches: dict[str, str] = {}
  ruled_out: set[str] = set()
  # Kept for reporting sessions left with no capture, after the loop: the
  # captures stored for each date set that report's severity, and a session
  # already named in an ambiguous match is skipped.
  captures_by_date: dict[datetime.date, list[str]] = {}
  ambiguous_stems: set[str] = set()
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

    captures_by_date.setdefault(traveller.date, []).append(
      traveller.reference.path
    )
    candidates = sessions_by_date.get(traveller.date, ())
    fitting = [
      session
      for session in candidates
      if not _leads_rule_out(traveller, session)
    ]
    if len(fitting) == 1:
      matches[traveller.reference.path] = stem_of(fitting[0])
    elif len(fitting) > 1:
      ambiguous_stems.update(stem_of(session) for session in fitting)
      issues.append(
        _AMBIGUOUS_SESSION_MATCH.issue(
          f'{traveller.reference.path} is dated {traveller.date}, and its '
          f'deals fit {len(fitting)} digitized sessions of that date equally '
          f'well ({", ".join(sorted(stem_of(one) for one in fitting))}); '
          f'assign it by hand'
        )
      )
    elif candidates:
      # Sessions share its date, but its deals fit none of them: every one
      # played some other game.
      ruled_out.add(traveller.reference.path)

  covered_stems = set(matches.values())
  for session in sessions:
    stem = stem_of(session)
    # An undated session already carries its issue from `parse_footer`, and one
    # named in an ambiguous match was already reported in that match's issue.
    if not session.date or stem in covered_stems or stem in ambiguous_stems:
      continue

    captures_of_date = captures_by_date.get(session.date)
    if captures_of_date:
      issues.append(
        _NO_CAPTURE_OF_DATE_FITS.issue(
          f'{stem} is dated {session.date}, and none of the captures of that '
          f'date ({", ".join(sorted(captures_of_date))}) fits its opening '
          f'leads; either '
          f'its own capture is not stored yet, or the sheet was misread badly '
          f'enough to rule it out'
        )
      )
    else:
      issues.append(
        _NO_CAPTURE_OF_DATE_STORED.issue(
          f'{stem} is dated {session.date}, and no capture of that date is '
          f'stored yet, so nothing enriches it'
        )
      )

  return issue_reporting.Read(
    Matches(sessions=matches, ruled_out=frozenset(ruled_out)), tuple(issues)
  )


def _leads_rule_out(traveller: Traveller, session: Session) -> bool:
  """Whether a sheet's opening leads show that a capture is of some other game.

  Each lead is checked against the capture's deal for the same board. A board
  lends no evidence either way when the capture states no deal for it, when the
  sheet records no played contract for it, or when the sheet records no lead. So
  a capture carrying no deals is never ruled out, and is placed by its date
  alone. A deal holding no hand for the seat on lead counts as a fit, since
  nothing in it contradicts the lead.
  """
  deals = {board.number: board.deal for board in traveller.boards if board.deal}

  checked_lead_count = 0
  impossible_lead_count = 0
  for board in session.boards:
    schedule = board.number.schedule
    deal = deals.get(schedule.number) if schedule else None
    resolution = board.outcome.resolution if board.outcome else None
    lead = board.opening_lead.card if board.opening_lead else None
    if not deal or not lead or not isinstance(resolution, PlayedContract):
      continue

    checked_lead_count += 1
    if deal_checks.find_lead_issues(
      deal, declarer=resolution.contract.declarer, opening_lead=lead
    ):
      impossible_lead_count += 1

  # TODO: a capture overlapping the sheet on only a board or two can be ruled
  # out by one misread lead. Real captures cover every board, and the session
  # left uncovered is reported, so no minimum count of checked leads is required
  # yet.
  return (
    impossible_lead_count
    > checked_lead_count * _TOLERATED_IMPOSSIBLE_LEAD_SHARE
  )


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
    session.session_key,
    session.source.image.content_hash,
    session.source.image.page,
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
