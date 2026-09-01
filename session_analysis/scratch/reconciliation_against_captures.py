# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Run the reconciliation join over the real captures on disk.

The unit tests build travellers by hand, which proves the join does what it says
on inputs it was told about. This runs it over the captures actually on disk,
which is the part no fixture can stand in for: whether the two publishers of one
real session agree closely enough to merge, and whether the sheet built from
them comes back clean.

It also seeds a row swap, because the failure mode swap detection exists for is
one no capture contains — a mistake made with a pen. Reconstructing the sheet
from the traveller and then transposing two rows is the nearest thing to the
real article, and it is what the detector is measured against.

There is no digitized sheet on disk to join to, so the sheet here is synthesized
from the traveller's own account of our row. That makes the faithful case a
tautology by construction — of course it agrees — and the point is what the runs
around it show: that merging two publishers loses nothing, that a seeded swap is
found without dragging its neighbours in, and that a session with no traveller
at all still comes back whole.
"""

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Sequence

from session_analysis import board_rotation, private_paths
from session_analysis.models import (
  Board,
  BoardNumber,
  Lead,
  Outcome,
  PlayedContract,
  Schedule,
  Session,
)
from session_analysis.testing import provenance
from session_analysis.travellers import Traveller
from session_analysis.unreviewed import reconciliation

# The session both publishers cover, as two captures of one club game. Named by
# their path under the records root, which is where `traveller_store` files
# them.
_DEFAULT_RECORDS = (
  'club/R260629M.html.json',
  'acbl_club/1472071.html.json',
)

# The pair of boards to transpose when seeding a swap — the same two the user
# actually filled in the wrong order on the 6/29 sheet.
_DEFAULT_SWAP = (20, 21)


@dataclasses.dataclass(frozen=True)
class _Report:
  """What one run of the join produced, reduced to what is worth printing."""

  boards: int
  enriched: int
  findings: tuple[str, ...]


def _load(records_root: pathlib.Path, names: Sequence[str]) -> list[Traveller]:
  """Read the stored travellers named, relative to the records root."""
  travellers = []
  for name in names:
    path = records_root / name
    if not path.is_file():
      raise FileNotFoundError(f'no stored traveller at {path}')
    travellers.append(Traveller.model_validate_json(path.read_text()))
  return travellers


def _sheet_row(
  number: int, enrichment: reconciliation.BoardEnrichment
) -> Board:
  """A sheet row holding what an enrichment says our pair did on a board.

  The opening lead is the one field a sheet owns outright, so it is taken from
  the deal rather than from the row: the card the leading seat actually held,
  which is what makes the lead-versus-deal check meaningful here.
  """
  resolution = enrichment.resolution
  lead = None
  if enrichment.deal and isinstance(resolution, PlayedContract):
    leader = resolution.contract.declarer.left_hand_opponent
    hand = enrichment.deal.hands.get(leader)
    if hand and hand.cards:
      card = hand.cards[0]
      lead = Lead(raw=f'{card.rank}{card.suit}', card=card)

  return Board(
    number=BoardNumber(
      raw=str(number),
      schedule=Schedule(
        number=number,
        dealer=board_rotation.dealer_for_board(number),
        vulnerability=board_rotation.vulnerability_for_board(number),
      ),
    ),
    outcome=Outcome(raw='', resolution=resolution),
    opening_lead=lead,
  )


def _build_sheet(
  enrichments: dict[int, reconciliation.BoardEnrichment],
  *,
  swap: tuple[int, int] | None,
) -> Session:
  """A digitized sheet standing in for the scan, optionally with two rows
  swapped.

  Swapping puts board `b`'s play in the row labelled `a` and the reverse, which
  is what filling two rows in the wrong order produces on paper.
  """
  boards = []
  for number in sorted(enrichments):
    holds = number
    if swap and number in swap:
      first, second = swap
      holds = second if number == first else first
    boards.append(_sheet_row(number, enrichments[holds]))

  return Session(
    event='reconciliation harness',
    source=provenance.sheet_source(path='synthesized', content_hash='none'),
    boards=tuple(boards),
  )


def _run(
  sheet: Session, travellers: Sequence[Traveller], our_name: str
) -> _Report:
  """Reconcile a sheet and reduce the result to a printable report."""
  session = reconciliation.reconcile_session(
    sheet, travellers, our_name=our_name
  )
  findings = [
    f'{issue.code} on board {board.number.raw}'
    for board in session.boards
    for issue in board.issues
  ]
  findings.extend(f'{issue.code} on the session' for issue in session.issues)
  return _Report(
    boards=len(session.boards),
    enriched=sum(1 for board in session.boards if board.deal),
    findings=tuple(findings),
  )


def _print(label: str, report: _Report) -> None:
  """Print one run's report under a heading."""
  print(f'--- {label}')
  print(f'    {report.enriched}/{report.boards} boards enriched')
  if not report.findings:
    print('    no findings')
  for finding in sorted(set(report.findings)):
    count = report.findings.count(finding)
    print(f'    {finding}{f" (x{count})" if count > 1 else ""}')


def main(argv: Sequence[str] | None = None) -> int:
  """Run the join over the stored captures and print what each pass found."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    '--name',
    required=True,
    help='the configured player name to match our row on',
  )
  parser.add_argument(
    '--record',
    action='append',
    dest='records',
    metavar='PATH',
    help=(
      'a stored traveller, by its path under the records root; repeatable. '
      f'Defaults to {" and ".join(_DEFAULT_RECORDS)}.'
    ),
  )
  arguments = parser.parse_args(argv)

  records_root = private_paths.discover_private_tree().traveller_records
  travellers = _load(records_root, arguments.records or _DEFAULT_RECORDS)

  # Each capture alone first, then merged: a field the merge loses that neither
  # source was missing is the failure this ordering is here to expose.
  for traveller in travellers:
    read = reconciliation.build_enrichments(
      [traveller], our_name=arguments.name
    )
    placed = sum(1 for board in read.value.values() if board.our_pair)
    print(
      f'{traveller.source:16} {len(read.value):3} boards, our row on {placed}'
    )

  merged = reconciliation.build_enrichments(travellers, our_name=arguments.name)
  placed = sum(1 for board in merged.value.values() if board.our_pair)
  print(f'{"merged":16} {len(merged.value):3} boards, our row on {placed}')
  print()

  _print(
    'faithful sheet',
    _run(
      _build_sheet(dict(merged.value), swap=None), travellers, arguments.name
    ),
  )
  _print(
    f'boards {_DEFAULT_SWAP[0]} and {_DEFAULT_SWAP[1]} swapped',
    _run(
      _build_sheet(dict(merged.value), swap=_DEFAULT_SWAP),
      travellers,
      arguments.name,
    ),
  )
  _print(
    'no travellers at all',
    _run(_build_sheet(dict(merged.value), swap=None), [], arguments.name),
  )
  return 0


if __name__ == '__main__':
  sys.exit(main())
