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
run read right and how many readings its runs got wrong. It then lists each cell
any run missed, with how many runs read that cell correctly and what the others
read instead.

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

from session_analysis.assembly import parse_and_assemble_session
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
  """One transcription run: its setting, source file, and transcribed rows."""

  setting: str
  path: pathlib.Path
  transcription: str
  raw_rows: tuple[Mapping[str, str], ...]


def load_runs(
  run_directories: Sequence[pathlib.Path], settled: Session
) -> Sequence[Run]:
  """Read every run, checking they all read one cutting of the settled scan.

  Raises:
    SystemExit: the runs read different cuttings, or a cutting of another scan
      than the one the settled session was ingested from, or the directories
      hold no run records.
  """
  settled_scan = pathlib.PurePosixPath(settled.source.image.path).name
  directories_by_digest: dict[str, set[str]] = collections.defaultdict(set)
  runs = []
  for directory in run_directories:
    manifest = json.loads((directory / _MANIFEST_PATH).read_text())
    cut_from = pathlib.Path(manifest['source_image']).name
    if cut_from != settled_scan:
      raise SystemExit(
        f'{directory} read strips cut from {cut_from}, but the settled'
        f' session was ingested from {settled_scan}'
      )
    for path in sorted(directory.glob('*.json')):
      record = json.loads(path.read_text())
      directories_by_digest[record['strips_digest']].add(str(directory))
      transcription = record['transcription']
      runs.append(
        Run(
          setting=f'{record["resolved_model"]} at {record["effort"]} effort',
          path=path,
          transcription=transcription,
          raw_rows=tuple(json.loads(transcription)['sheet']['boards']),
        )
      )
  # Runs over different crops would measure the cutting as much as the setting,
  # so mixed cuttings are refused, as in `voted_session_comparison.py`.
  if len(directories_by_digest) > 1:
    listing = '; '.join(
      f'{digest} in {", ".join(sorted(directories))}'
      for digest, directories in sorted(directories_by_digest.items())
    )
    raise SystemExit(f'the runs read different strip sets: {listing}')
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


def report(
  tallies: Sequence[CellTally],
  runs: Sequence[Run],
  settled_path: pathlib.Path,
) -> Iterator[str]:
  """The comparison as lines: a summary per setting, then each missed cell."""
  run_counts = collections.Counter(run.setting for run in runs)
  settings = sorted(run_counts)
  width = max(len(setting) for setting in settings)

  yield f'answer key: {settled_path.name}, {len(tallies)} cells'
  yield ''
  yield f'{"":{width}}  runs  cells every run read right  misread readings'
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
    yield (
      f'{setting:{width}}  {run_counts[setting]:4d}'
      f'  {always_right:26d}  {misread:16d}'
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
    help="the sheet's session record, from bridge-private's sessions/",
  )
  arguments = parser.parse_args()

  settled = Session.model_validate_json(arguments.settled_session.read_text())
  runs = load_runs(arguments.run_directories, settled)
  tallies = tally_cells(runs, settled)
  for line in report(tallies, runs, arguments.settled_session):
    print(line)


if __name__ == '__main__':
  main()
