# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Score each setting's two strip runs the way the pipeline itself does.

Diffing two transcriptions as raw strings answers the wrong question, in both
directions: the voting pass compares parsed values, so `X` and `*` never reach a
reviewer, while a run-together `1N2C2D3N` offers the parser no seam to split on
and becomes one unresolved call rather than four bids. Which spacing differences
matter is not eyeballable, so this runs each model's pair of runs through
`assembly.parse_and_assemble_voted_session` and reports the issues that survive
— what a review queue would actually hold.

The last step of the extraction model comparison, reading the run JSON that
`strips_model_comparison.py transcribe` wrote — see this directory's README.md
for what the comparison is for and how to run every step.
"""

import argparse
import collections
import datetime
import json
import pathlib

from session_analysis.assembly import parse_and_assemble_voted_session
from session_analysis.testing import provenance

# Provenance nothing here reads: this comparison starts from run JSON already on
# disk, so it never sees a scan, and the stand-in frame is as true as any.
_SOURCE = provenance.sheet_source(
  path='strips-comparison', content_hash='comparison'
)


def main() -> None:
  """Vote each setting's two runs against each other and tally the issues."""
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

  by_setting: dict[str, dict[int, str]] = collections.defaultdict(dict)
  runs_by_digest: dict[str, list[str]] = collections.defaultdict(list)
  for path in sorted(arguments.run_directory.glob('*.json')):
    record = json.loads(path.read_text())
    # Group by what answered rather than by what was asked for: an alias and the
    # release it resolves to name one setting and must not split into two.
    label = f'{record["resolved_model"]} at {record["effort"]} effort'
    by_setting[label][record['run_index']] = record['transcription']
    runs_by_digest[record['strips_digest']].append(path.name)

  if not runs_by_digest:
    parser.error(f'no run records in {arguments.run_directory}')
  # Arms compared over different crops measure the cutting as much as the
  # setting, so a directory mixing cuttings is refused rather than scored.
  if len(runs_by_digest) > 1:
    parser.error(
      f'runs in {arguments.run_directory} read different strip sets:'
      f' {dict(runs_by_digest)}'
    )
  print(f'all runs read strip set {next(iter(runs_by_digest))}')

  for label, runs in sorted(by_setting.items()):
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
      f'=== {label}: {len(board_issues)} issues over '
      f'{len(session.boards)} boards'
    )
    for code, count in sorted(counts.items()):
      print(f'  {count:3d}  {code}')
    for raw_number, issue in board_issues:
      print(f'  board {raw_number}: [{issue.code}] {issue.message}')


if __name__ == '__main__':
  main()
