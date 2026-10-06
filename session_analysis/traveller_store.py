# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Turning the captures on disk into the stored game record.

A capture is whatever a publishing site handed over — a BridgeComposer recap, a
PBN deal file, or an ACBL results page. The stored record is that same session
in this project's own shapes, written as JSON; travellers.md `#traveller-model`
covers that shape. This module is the step between: it walks the capture root,
hands each capture to the parser that reads its format, and writes the parsed
traveller beneath the records root.

The module also solves each deal's double-dummy table for its record. A source
may publish that table only in part, so the record gains all twenty cells —
solved once, here, rather than by each reader that needs them. Every cell the
source did publish is checked against the solved one, and any disagreement is
reported.

Parsing reads captures off disk rather than running as part of each fetch,
because two things that need it involve no fetch at all. A capture saved by hand
is the acquisition fallback for whatever the fetchers cannot reach, and never
passes through them. And demonstrating that a parser change altered nothing
means re-parsing every capture on hand and diffing the records, which
re-fetching could not stand in for — a site makes no promise to serve the same
bytes twice. Keeping the raw captures is what makes both possible, and this
module is what reads them back.

A capture's directory picks its parser, one directory per publishing site,
because nothing inside a capture reliably announces its own format — the ACBL
login page a gated game answers with parses as far as "no page data" rather than
declining to be an ACBL page at all. A directory per site keeps that judgment
where a person makes it once, at filing time, and gives a hand-saved capture the
same standing as a fetched one.

Records mirror the captures: a capture at `club/sub/dir/foo.pbn` stores as
`club/sub/dir/foo.pbn.json`. Each record keeps its capture's whole name,
extension and all, so two captures of one game cannot collide. The filename
mirroring means that a capture's record can be located without opening anything,
which lets a run tell at a glance which captures still need processing.

A run does only that work: a capture whose record already postdates it is left
alone. Parsing everything again is only needed for a parser change, not for a
routine run, so it waits to be asked for through `refresh`.

`store_travellers` does only the file handling: walking the capture root,
reading captures, and writing records. `parse_captures` makes every decision
about a capture's content, so those decisions can be exercised without a disk.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol

from session_analysis import (
  acbl_club_parsing,
  acbl_tournament_parsing,
  capture_urls,
  club_html_parsing,
  club_pbn_parsing,
  issue_reporting,
)
from session_analysis.enums import IssueSeverity
from session_analysis.models import (
  CaptureReference,
  Issue,
  SolvedDoubleDummyTricks,
)
from session_analysis.private_paths import (
  ACBL_CLUB_CAPTURE_DIRECTORY,
  ACBL_TOURNAMENT_CAPTURE_DIRECTORY,
  CLUB_CAPTURE_DIRECTORY,
  PrivateTree,
)
from session_analysis.travellers import Traveller, TravellerBoard
from session_analysis.unreviewed import deal_checks, double_dummy_solving

# A capture that yielded no record. Both are worth a person's attention rather
# than a log line nothing reads: the first says a file is filed where no parser
# expects it, and the second that a page held nothing to store — a saved login
# page, or a team game's ACBL page that carries no per-board rows.
_UNRECOGNIZED_CAPTURE = issue_reporting.Failure(
  'unrecognized_capture', IssueSeverity.MEDIUM, 'capture'
)
_CAPTURE_HELD_NO_BOARDS = issue_reporting.Failure(
  'capture_held_no_boards', IssueSeverity.MEDIUM, 'capture'
)

# A published double-dummy cell that the deal published beside it does not bear
# out. Either a parser misread the table or the deal, or the source printed a
# table for some other deal. Since the solved table that sessions carry rests on
# that same deal, the disagreement deserves a person's attention.
_PUBLISHED_TABLE_DISAGREES = issue_reporting.Failure(
  'published_double_dummy_disagrees',
  IssueSeverity.MEDIUM,
  'double_dummy_tricks',
)

_PBN_SUFFIX = '.pbn'
_HTML_SUFFIXES = frozenset({'.htm', '.html'})


@dataclasses.dataclass(frozen=True)
class Capture:
  """One capture as its site published it, and where it was fetched from."""

  # Bytes rather than text, because a capture is decoded only once a parser
  # recognizes it: a misfiled PDF is reported as unrecognized rather than
  # failing to decode.
  content: bytes
  # None for a capture saved by hand.
  url: str | None = None


class _CaptureParser(Protocol):
  """Reads one capture's whole text into the traveller it records."""

  def __call__(
    self, text: str, *, reference: CaptureReference
  ) -> Traveller: ...


def _parser_for(site: str, suffix: str) -> _CaptureParser | None:
  """The parser for a capture's site and extension, or None if there is none.

  Args:
    site: the capture root subdirectory the capture sits in, naming the site
      that published it.
    suffix: the capture's file extension. The club publishes both a PBN deal
      file and an HTML recap per game and the two share a directory, so within
      the club's captures the extension tells the formats apart; the
      two ACBL directories hold HTML alone.
  """
  suffix = suffix.lower()
  if site == CLUB_CAPTURE_DIRECTORY:
    if suffix == _PBN_SUFFIX:
      return club_pbn_parsing.parse_club_pbn
    if suffix in _HTML_SUFFIXES:
      return club_html_parsing.parse_club_html
    return None
  if suffix not in _HTML_SUFFIXES:
    return None
  if site == ACBL_CLUB_CAPTURE_DIRECTORY:
    return acbl_club_parsing.parse_acbl_club_html
  if site == ACBL_TOURNAMENT_CAPTURE_DIRECTORY:
    return acbl_tournament_parsing.parse_acbl_tournament_html
  return None


def _is_current(record: Path, capture: Path) -> bool:
  """Whether `record` was written after everything it was derived from.

  A capture and its URL sidecar both feed the record, and a fetch writes them
  moments apart — but a sidecar added by hand later would otherwise leave the
  record carrying no URL until something else disturbed the capture.
  """
  if not record.is_file():
    return False

  sources = (capture, capture_urls.sidecar_for(capture))
  newest_source = max(
    source.stat().st_mtime for source in sources if source.is_file()
  )
  return record.stat().st_mtime > newest_source


def _captures_in(site_directory: Path) -> Sequence[Path]:
  """Every file under a site directory that could be a capture.

  Leaves out the URL sidecars the fetchers write beside their captures, and
  anything whose name starts with a dot — `.DS_Store` rides along in these
  directories and is not worth a complaint on every run.
  """
  return sorted(
    path
    for path in site_directory.rglob('*')
    if path.is_file()
    and path.suffix != capture_urls.URL_SUFFIX
    and not path.name.startswith('.')
  )


def record_for(tree: PrivateTree, capture_path: PurePosixPath | str) -> Path:
  """Where the record parsed from a capture is filed.

  A record keeps its capture's whole name and adds `.json`, so two captures of
  one game cannot collide and a capture's record is located without opening
  anything. `capture_path` is relative to the capture root, which is the
  spelling `CaptureReference` keeps.
  """
  return tree.traveller_records / f'{capture_path}.json'


def store_travellers(
  tree: PrivateTree, *, refresh: bool = False
) -> issue_reporting.Read[Sequence[PurePosixPath]]:
  """Parse the captures under `tree` that need it, and write their records.

  `parse_captures` decides what each capture yields and what is reported about
  it; this function only reads and writes.

  Args:
    tree: the private tree whose capture root is read and whose records root is
      written.
    refresh: parse every capture, including those whose record already
      postdates it. Used to validate parser changes.

  Returns:
    The captures this run stored, by their path relative to the capture root,
    alongside the issues from `parse_captures` and one for each URL sidecar
    that could not be read. A capture left alone as current appears in
    neither, so a routine run over an unchanged tree reports nothing at all.
    The travellers themselves are not handed back — the records on disk are
    the durable copy, and anything wanting one reads it there whether this run
    wrote it or an earlier one did.

  Raises:
    FileNotFoundError: if the capture root does not exist.
  """
  captures_root = tree.traveller_captures
  if not captures_root.is_dir():
    raise FileNotFoundError(f'no traveller capture root at {captures_root}')

  captures: dict[PurePosixPath, Capture] = {}
  issues: list[Issue] = []
  for site_directory in sorted(
    path for path in captures_root.iterdir() if path.is_dir()
  ):
    for capture_file in _captures_in(site_directory):
      relative_to_root = PurePosixPath(capture_file.relative_to(captures_root))
      record = record_for(tree, relative_to_root)
      if not refresh and _is_current(record, capture_file):
        continue

      recorded_url = capture_urls.read_url(capture_file)
      issues.extend(recorded_url.issues)
      captures[relative_to_root] = Capture(
        capture_file.read_bytes(), url=recorded_url.value
      )

  parsed = parse_captures(captures)
  for relative_to_root, traveller in parsed.value.items():
    record = record_for(tree, relative_to_root)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(traveller.model_dump_json(indent=2) + '\n')

  return issue_reporting.Read(tuple(parsed.value), (*issues, *parsed.issues))


def parse_captures(
  captures: Mapping[PurePosixPath, Capture],
) -> issue_reporting.Read[Mapping[PurePosixPath, Traveller]]:
  """Parse captures held in memory into the travellers they record.

  Two kinds of capture are left out and reported as issues rather than raising:
  one whose site and extension match no parser, and one that parses to no boards
  at all. A run over a whole tree should not stop at one odd file, any more than
  a parser stops at one odd row (travellers.md `#issue-reporting`).

  Args:
    captures: keyed by each capture's path relative to the capture root. The
      path's first directory names the site that published the capture.

  Returns:
    The traveller each capture parses to, with every well-formed deal's
    double-dummy table solved, keyed by the same path. Alongside it, an issue
    for every capture that yielded nothing, and for every board whose published
    double-dummy table its deal does not bear out.
  """
  travellers: dict[PurePosixPath, Traveller] = {}
  issues: list[Issue] = []
  for path, capture in captures.items():
    parse = _parser_for(path.parts[0], path.suffix)
    if not parse:
      issues.append(_UNRECOGNIZED_CAPTURE.issue(f'no parser reads {path}'))
      continue

    traveller = parse(
      _decoded(capture.content),
      reference=CaptureReference(path=str(path), url=capture.url),
    )
    if not traveller.boards:
      issues.append(
        _CAPTURE_HELD_NO_BOARDS.issue(
          f'{path} parsed as {traveller.source} but holds no boards, so '
          f'nothing was stored for it: {traveller.event!r}'
        )
      )
      continue

    solved = _with_solved_tables(traveller)
    issues.extend(solved.issues)
    travellers[path] = solved.value

  return issue_reporting.Read(travellers, tuple(issues))


def _decoded(content: bytes) -> str:
  """A capture's text, decoded as UTF-8 with every line ending in `\\n`.

  Many captures end their lines in `\\r\\n`; converting those endings means no
  parser ever sees a carriage return.
  """
  # TODO: decode by the charset a capture declares rather than assuming UTF-8.
  # Every capture on hand reads clean, and one that did not would raise rather
  # than mislead, so this waits on a capture that exercises it.
  return content.decode().replace('\r\n', '\n').replace('\r', '\n')


def _with_solved_tables(
  traveller: Traveller,
) -> issue_reporting.Read[Traveller]:
  """The traveller, with each well-formed deal's double-dummy table solved.

  Each cell the source published is checked against the solved one. A
  disagreement goes two places: into the issues returned beside the traveller,
  and onto the board, where the stored record keeps it.
  """
  boards: list[TravellerBoard] = []
  issues: list[Issue] = []
  for board in traveller.boards:
    # A malformed deal goes unsolved, and unreported here: wherever
    # reconciliation joins it to a sheet, the same
    # `deal_checks.find_deal_issues` reports what is wrong with it.
    if not board.deal or deal_checks.find_deal_issues(board.deal):
      boards.append(board)
      continue

    solved = double_dummy_solving.solve_table(board.deal)
    disagreement = _published_disagreement(
      board, solved, capture=traveller.reference.path
    )
    board_issues = board.issues
    if disagreement:
      issues.append(disagreement)
      board_issues = (*board_issues, disagreement)
    boards.append(
      board.model_copy(
        update={'solved_double_dummy_tricks': solved, 'issues': board_issues}
      )
    )

  return issue_reporting.Read(
    traveller.model_copy(update={'boards': tuple(boards)}), tuple(issues)
  )


def _published_disagreement(
  board: TravellerBoard, solved: SolvedDoubleDummyTricks, *, capture: str
) -> Issue | None:
  """One report naming every published cell the solved table contradicts.

  None where the two agree, and where nothing was published to check.
  """
  if not board.double_dummy_tricks:
    return None

  cells = [
    f'{seat.name.lower()} in {strain.name.lower()} published {published}, '
    f'solved {solved[seat][strain]}'
    for seat, row in board.double_dummy_tricks.items()
    for strain, published in row.items()
    # A cell the source left unstated contradicts nothing; zero tricks is a
    # stated count, so the test is for None rather than for falsiness.
    if published is not None and published != solved[seat][strain]
  ]
  if not cells:
    return None

  return _PUBLISHED_TABLE_DISAGREES.issue(
    f'{capture} board {board.number}: the published double-dummy table '
    f'disagrees with the deal beside it — {"; ".join(cells)}'
  )
