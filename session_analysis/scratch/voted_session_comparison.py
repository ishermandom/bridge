# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Score each model's two strip runs the way the pipeline itself does.

Diffing two transcriptions as raw strings answers the wrong question, in both
directions: the voting pass compares parsed values, so `X` and `*` never reach a
reviewer, while a run-together `1N2C2D3N` offers the parser no seam to split on
and becomes one unresolved call rather than four bids. Which spacing differences
matter is not eyeballable, so this runs each model's pair of runs through
`assembly.parse_and_assemble_voted_session` and reports the issues that survive
— what a review queue would actually hold.

Step two of the extraction model comparison, reading the run JSON that
`strips_model_comparison.py` wrote — see this directory's README.md for what the
comparison is for and how to run both steps.
"""

import argparse
import collections
import datetime
import json
import pathlib

from session_analysis.assembly import parse_and_assemble_voted_session
from session_analysis.models import SheetImage, Source

_SOURCE = Source(
  image=SheetImage(path='strips-comparison', content_hash='comparison')
)


def main() -> None:
  """Vote each model's two runs against each other and tally the issues."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--run-directory', type=pathlib.Path, required=True)
  # Scoresheet footers often write a month/day with no year, which the parser
  # resolves against a date known to fall after the session. Anything later than
  # the sheet works; the default suits the 6/29 sheet the spec's figures came
  # from, and a sheet from another year needs its own.
  parser.add_argument(
    '--reference-date',
    type=datetime.date.fromisoformat,
    default=datetime.date(2026, 7, 1),
  )
  arguments = parser.parse_args()

  by_model: dict[str, dict[int, str]] = collections.defaultdict(dict)
  for path in sorted(arguments.run_directory.glob('*.json')):
    record = json.loads(path.read_text())
    by_model[record['model']][record['run_index']] = record['transcription']

  for model, runs in sorted(by_model.items()):
    session = parse_and_assemble_voted_session(
      runs[1], runs[2], _SOURCE, reference_date=arguments.reference_date
    )
    board_issues = [
      (board.number.raw, issue)
      for board in session.boards
      for issue in board.issues
    ]
    counts = collections.Counter(issue.code for _, issue in board_issues)
    print(
      f'=== {model}: {len(board_issues)} issues over '
      f'{len(session.boards)} boards'
    )
    for code, count in sorted(counts.items()):
      print(f'  {count:3d}  {code}')
    for raw_number, issue in board_issues:
      print(f'  board {raw_number}: [{issue.code}] {issue.message}')


if __name__ == '__main__':
  main()
