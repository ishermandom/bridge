# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Judge every run's reading of every board cell against a settled session.

`voted_session_comparison.py` reports what a review queue would hold, which says
how often a model disagrees with itself but not how often it is right. A settled
session — one reconciled against the travellers and reviewed with the user — is
an answer key. So this script parses each run alone, without voting it against
another, and marks each of that run's cells correct or misread against the
settled record.

For each setting (a model at one effort level), it reports how many cells every
run read right, how many readings its runs got wrong, and what a run cost. It
then votes each sweep's two runs against each other, as ingest does, and reports
how many boards the votes sent to review and how many wrong cells they let
through unflagged. Last, it lists each cell any run missed, with how many runs
read that cell correctly and what the others read instead.

An optional last step of the extraction model comparison, for a sheet that has a
settled session — see this directory's README.md for every step, and for what
the answer key can and cannot vouch for.
"""

import argparse
import collections
import dataclasses
import datetime
import enum
import json
import pathlib
from collections.abc import Iterator, Mapping, Sequence

from session_analysis.assembly import (
  parse_and_assemble_session,
  parse_and_assemble_voted_session,
)
from session_analysis.models import Board, Session
from session_analysis.testing import provenance

# A stand-in provenance: parsing requires one, but each run is parsed only to be
# compared, and nothing reads it.
_SOURCE = provenance.sheet_source(
  path='settled-comparison', content_hash='comparison'
)
_MANIFEST_PATH = pathlib.Path('strips', 'manifest.json')


class Cell(enum.StrEnum):
  """A board's judged cells, each named for its column on the sheet.

  The values are the keys of a board row in the raw transcription.
  """

  NUMBER = 'board_number'
  AUCTION = 'auction'
  CONTRACT = 'contract'
  LEAD = 'lead'
  NOTES = 'notes'


def parsed_reading(board: Board, cell: Cell) -> object:
  """One cell's parse as JSON-ready data.

  Includes the marks parsed out of the cell's text, such as a board number's
  circle.
  """
  match cell:
    case Cell.NUMBER:
      # A circle around the number sets the board's `flagged_for_review`. It is
      # drawn in the number's cell, so it is judged with the number.
      return [board.number.model_dump(mode='json'), board.flagged_for_review]
    case Cell.AUCTION:
      return [entry.model_dump(mode='json') for entry in board.auction]
    case Cell.CONTRACT:
      return board.outcome.model_dump(mode='json') if board.outcome else None
    case Cell.LEAD:
      lead = board.opening_lead
      return lead.model_dump(mode='json') if lead else None
    case Cell.NOTES:
      return board.notes


def comparison_key(reading: object) -> str:
  """A reading's comparison string: its parse, minus `raw` and `issues`.

  `raw` is dropped so that spacing the parser ignores compares equal: `4C W+4`
  and `4CW+4` get one key. `issues` is dropped because it describes the parse
  rather than the ink, and a settled record has had its issues resolved.
  """

  def without_raw_and_issues(value: object) -> object:
    if isinstance(value, dict):
      return {
        key: without_raw_and_issues(item)
        for key, item in value.items()
        if key not in ('raw', 'issues')
      }
    if isinstance(value, list):
      return [without_raw_and_issues(item) for item in value]
    return value

  return json.dumps(without_raw_and_issues(reading), sort_keys=True)


def settled_rendering(board: Board, cell: Cell) -> str:
  """A settled cell spelled from its record's `raw` text and marks.

  Only a fallback, for an answer no run read. A correction in review can change
  a parsed value without updating its `raw` text, so the settled `raw` may be
  stale. A run that read the answer transcribed it directly, so that run's text
  is preferred.
  """
  match cell:
    case Cell.NUMBER:
      number = board.number.raw
      return f'({number})' if board.flagged_for_review else number
    case Cell.AUCTION:
      return ' '.join(
        f'({entry.raw})' if entry.by_opponents else entry.raw
        for entry in board.auction
      )
    case Cell.CONTRACT:
      return board.outcome.raw if board.outcome else ''
    case Cell.LEAD:
      return board.opening_lead.raw if board.opening_lead else ''
    case Cell.NOTES:
      return board.notes or ''


@dataclasses.dataclass
class CellTally:
  """One cell's answer, and how every setting's runs read it."""

  board_number: str
  cell: Cell
  answer_comparison_key: str
  answer_as_settled: str
  # The answer as a run transcribed it, once any run has.
  answer_as_read: str | None = None
  correct_runs: collections.Counter[str] = dataclasses.field(
    default_factory=collections.Counter
  )
  # Maps each misreading's key to how many of each setting's runs read it.
  misread_runs: dict[str, collections.Counter[str]] = dataclasses.field(
    default_factory=lambda: collections.defaultdict(collections.Counter)
  )
  # Maps each misreading's key to the first run's text for it.
  misreading_as_read: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Run:
  """One transcription run: its setting, source file, rows, and cost."""

  setting: str
  path: pathlib.Path
  # Which of its sweep's two runs of this setting it was: 1 or 2.
  run_index: int
  transcription: str
  raw_rows: tuple[Mapping[str, str], ...]
  cost_usd: float


@dataclasses.dataclass
class VoteTally:
  """What one setting's votes would hand ingest, summed over its sweeps."""

  vote_count: int = 0
  boards_sent_to_review: int = 0
  wrong_cells_let_through: int = 0


def load_runs(
  strips_from: pathlib.Path,
  run_directories: Sequence[pathlib.Path],
  settled: Session,
) -> Sequence[Run]:
  """Read every run, checking they all read the given cutting of the settled
  scan.

  Raises:
    SystemExit: the strips were cut from another scan than the one the settled
      session was ingested from, a run read other strips or a different prompt
      than the rest, or the directories hold no run records.
  """
  settled_scan = pathlib.PurePosixPath(settled.source.image.path).name
  manifest = json.loads((strips_from / _MANIFEST_PATH).read_text())
  cut_from = pathlib.Path(manifest['source_image']).name
  if cut_from != settled_scan:
    raise SystemExit(
      f'{strips_from} holds strips cut from {cut_from}, but the settled'
      f' session was ingested from {settled_scan}'
    )
  runs_by_prompt: dict[str, list[str]] = collections.defaultdict(list)
  runs = []
  for directory in run_directories:
    for path in sorted(directory.glob('*.json')):
      record = json.loads(path.read_text())
      # Runs over other crops would measure the cutting as much as the setting.
      if record['strips_digest'] != manifest['digest']:
        raise SystemExit(
          f'{path} read strip set {record["strips_digest"]}, not the'
          f' {manifest["digest"]} in {strips_from}'
        )
      # A record written before runs carried a prompt digest cannot say which
      # prompt it read, so it counts as reading an unknown one.
      runs_by_prompt[record.get('prompt_digest', 'unrecorded')].append(
        str(path)
      )
      transcription = record['transcription']
      runs.append(
        Run(
          setting=f'{record["resolved_model"]} at {record["effort"]} effort',
          path=path,
          run_index=record['run_index'],
          transcription=transcription,
          raw_rows=tuple(json.loads(transcription)['sheet']['boards']),
          cost_usd=record['cost_usd'],
        )
      )
  # A changed prompt changes what every setting was asked to do, so runs under
  # different prompts would measure the change rather than the settings.
  if len(runs_by_prompt) > 1:
    listing = '; '.join(
      f'{digest} in {len(paths)} runs, such as {paths[0]}'
      for digest, paths in sorted(runs_by_prompt.items())
    )
    raise SystemExit(f'the runs read different prompts: {listing}')
  if not runs:
    raise SystemExit('no run records in the given directories')
  return runs


def tally_cells(runs: Sequence[Run], settled: Session) -> Sequence[CellTally]:
  """Judge every run's every cell against the settled session.

  Rows are matched by position: each strip is one printed row, so a run's nth
  row and the settled session's nth board come from the same line of the sheet.
  """
  tallies = [
    CellTally(
      board_number=board.number.raw,
      cell=cell,
      answer_comparison_key=comparison_key(parsed_reading(board, cell)),
      answer_as_settled=settled_rendering(board, cell),
    )
    for board in settled.boards
    for cell in Cell
  ]
  # The parser needs a reference date to complete the footer's handwritten date,
  # such as its year. The footer date is never judged, so any date on or after
  # the session will do; today's serves when the record has none.
  reference_date = settled.date or datetime.date.today()
  for run in runs:
    session = parse_and_assemble_session(
      run.transcription, _SOURCE, reference_date=reference_date
    )
    if len(session.boards) != len(settled.boards):
      raise SystemExit(
        f'{run.path} read {len(session.boards)} rows where the settled'
        f' session has {len(settled.boards)}'
      )
    # `tallies` runs board by board, each in `Cell` order, and so do these
    # readings, so zipping pairs every tally with the same cell in this run.
    readings = (
      (board, raw_row, cell)
      for board, raw_row in zip(session.boards, run.raw_rows, strict=True)
      for cell in Cell
    )
    for tally, (board, raw_row, cell) in zip(tallies, readings, strict=True):
      key = comparison_key(parsed_reading(board, cell))
      as_read = raw_row.get(cell, '')
      if key == tally.answer_comparison_key:
        tally.correct_runs[run.setting] += 1
        tally.answer_as_read = tally.answer_as_read or as_read
      else:
        tally.misread_runs[key][run.setting] += 1
        tally.misreading_as_read.setdefault(key, as_read)
  return tallies


def holds_issue(value: object) -> bool:
  """Whether a dumped board carries an issue anywhere, on it or on any cell."""
  if isinstance(value, dict):
    return bool(value.get('issues')) or any(
      holds_issue(item) for item in value.values()
    )
  if isinstance(value, list):
    return any(holds_issue(item) for item in value)
  return False


def tally_votes(
  runs: Sequence[Run], settled: Session
) -> Mapping[str, VoteTally]:
  """Vote each sweep's two runs of a setting, as ingest does, and judge it.

  A board left with any issue goes to a reviewer, who would see a misread there.
  A misread on a board with no issue reaches the record unflagged.
  """
  # A sweep's directory holds runs 1 and 2 of each setting it ran.
  pairs: dict[tuple[pathlib.Path, str], dict[int, Run]] = (
    collections.defaultdict(dict)
  )
  for run in runs:
    pairs[run.path.parent, run.setting][run.run_index] = run

  reference_date = settled.date or datetime.date.today()
  tallies: dict[str, VoteTally] = collections.defaultdict(VoteTally)
  for (directory, setting), pair in sorted(pairs.items()):
    if sorted(pair) != [1, 2]:
      raise SystemExit(
        f'{directory} holds runs {sorted(pair)} of {setting}, not a pair'
      )
    voted = parse_and_assemble_voted_session(
      pair[1].transcription,
      pair[2].transcription,
      _SOURCE,
      reference_date=reference_date,
    )
    tally = tallies[setting]
    tally.vote_count += 1
    # Each run already matched the settled row count in `tally_cells`, so the
    # voted boards do too.
    for board, settled_board in zip(voted.boards, settled.boards, strict=True):
      if holds_issue(board.model_dump(mode='json')):
        tally.boards_sent_to_review += 1
        continue
      tally.wrong_cells_let_through += sum(
        1
        for cell in Cell
        if comparison_key(parsed_reading(board, cell))
        != comparison_key(parsed_reading(settled_board, cell))
      )
  return tallies


def report(
  tallies: Sequence[CellTally],
  vote_tallies: Mapping[str, VoteTally],
  runs: Sequence[Run],
  settled_path: pathlib.Path,
) -> Iterator[str]:
  """The comparison as lines: two summaries per setting, then each missed cell."""
  run_counts = collections.Counter(run.setting for run in runs)
  costs: dict[str, float] = collections.defaultdict(float)
  for run in runs:
    costs[run.setting] += run.cost_usd
  settings = sorted(run_counts)
  width = max(len(setting) for setting in settings)

  yield f'answer key: {settled_path.name}, {len(tallies)} cells'
  yield ''
  yield 'each run read alone:'
  yield (
    f'{"":{width}}  runs  cells every run read right  misread readings'
    '  cost per run'
  )
  for setting in settings:
    always_right = sum(
      1
      for tally in tallies
      if tally.correct_runs[setting] == run_counts[setting]
    )
    misread = sum(
      counts[setting]
      for tally in tallies
      for counts in tally.misread_runs.values()
    )
    cost_per_run = costs[setting] / run_counts[setting]
    yield (
      f'{setting:{width}}  {run_counts[setting]:4d}'
      f'  {always_right:26d}  {misread:16d}  {f"${cost_per_run:.3f}":>12}'
    )

  yield ''
  yield "each sweep's two runs voted, as ingest does:"
  yield (
    f'{"":{width}}  votes  boards sent to review'
    '  wrong cells let through unflagged'
  )
  for setting in settings:
    vote = vote_tallies[setting]
    yield (
      f'{setting:{width}}  {vote.vote_count:5d}'
      f'  {vote.boards_sent_to_review:21d}'
      f'  {vote.wrong_cells_let_through:33d}'
    )

  for tally in tallies:
    if not tally.misread_runs:
      continue
    if tally.answer_as_read is None:
      answer = f'{tally.answer_as_settled!r} (as settled; no run read it)'
    else:
      answer = repr(tally.answer_as_read)
    yield ''
    yield (
      f'board {tally.board_number}, {tally.cell.name.lower()}: answer {answer}'
    )
    for setting in settings:
      yield (
        f'  {setting:{width}}  {tally.correct_runs[setting]:2d} of'
        f' {run_counts[setting]} correct'
      )
      for key, counts in tally.misread_runs.items():
        if counts[setting]:
          yield (
            f'    {counts[setting]:2d} misread as'
            f' {tally.misreading_as_read[key]!r}'
          )


def main() -> None:
  """Judge the given runs against a settled session and print the result."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    '--strips-from',
    type=pathlib.Path,
    required=True,
    help='the directory `strips_model_comparison.py cut` wrote',
  )
  parser.add_argument(
    '--run-directories',
    type=pathlib.Path,
    nargs='+',
    required=True,
    help='output directories of `strips_model_comparison.py transcribe`',
  )
  parser.add_argument(
    '--settled-session',
    type=pathlib.Path,
    required=True,
    help="the sheet's answer key, such as its record in bridge-private's"
    ' sessions/',
  )
  arguments = parser.parse_args()

  settled = Session.model_validate_json(arguments.settled_session.read_text())
  runs = load_runs(arguments.strips_from, arguments.run_directories, settled)
  tallies = tally_cells(runs, settled)
  vote_tallies = tally_votes(runs, settled)
  for line in report(tallies, vote_tallies, runs, arguments.settled_session):
    print(line)


if __name__ == '__main__':
  main()
