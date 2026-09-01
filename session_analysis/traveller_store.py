# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Turning the captures on disk into the stored game record.

A capture is whatever a publishing site handed over — a BridgeComposer recap, a
PBN deal file, or an ACBL results page. The stored record is that same session
in this project's own shapes, written as JSON; travellers.md `#traveller-model`
covers that shape. This module is the step between: it walks the capture root,
hands each capture to the parser that reads its format, and writes the parsed
traveller beneath the records root.

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
"""

from collections.abc import Sequence
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
from session_analysis.private_paths import (
  ACBL_CLUB_CAPTURE_DIRECTORY,
  ACBL_TOURNAMENT_CAPTURE_DIRECTORY,
  CLUB_CAPTURE_DIRECTORY,
  PrivateTree,
)
from session_analysis.travellers import CaptureReference, Traveller

# A capture that yielded no record. Both are worth a person's attention rather
# than a log line nothing reads: the first says a file is filed where no parser
# expects it, and the second that a page held nothing to store — a saved login
# page, or a team game, which has no per-board rows at all.
_UNRECOGNIZED_CAPTURE = issue_reporting.Failure(
  'unrecognized_capture', IssueSeverity.MEDIUM, 'capture'
)
_CAPTURE_HELD_NO_BOARDS = issue_reporting.Failure(
  'capture_held_no_boards', IssueSeverity.MEDIUM, 'capture'
)

_PBN_SUFFIX = '.pbn'
_HTML_SUFFIXES = frozenset({'.htm', '.html'})


class _CaptureParser(Protocol):
  """Reads one capture's whole text into the traveller it records."""

  def __call__(
    self, text: str, *, reference: CaptureReference
  ) -> Traveller: ...


def _parser_for(site: str, suffix: str) -> _CaptureParser | None:
  """The parser that reads a capture, or None for a file no parser claims.

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


def store_travellers(
  tree: PrivateTree, *, refresh: bool = False
) -> issue_reporting.Read[Sequence[PurePosixPath]]:
  """Parse the captures under `tree` that need it, and write their records.

  A capture no parser claims, and one that parses to no boards at all, are both
  left unstored and reported as issues rather than raising: a run over a whole
  tree should not stop at one odd file, and the same discipline the parsers hold
  to inside a capture holds here across them (travellers.md `#issue-reporting`).

  Args:
    tree: the private tree whose capture root is read and whose records root is
      written.
    refresh: parse every capture, including those whose record already
      postdates it. Used to validate parser changes.

  Returns:
    The captures this run parsed, by their path relative to the capture root,
    alongside an issue for every capture that yielded nothing. A capture left
    alone as current is neither, so a routine run over an unchanged tree
    reports nothing at all. The travellers themselves are not handed back —
    the records on disk are the durable copy, and anything wanting one reads
    it there whether this run wrote it or an earlier one did.

  Raises:
    FileNotFoundError: if the capture root does not exist.
  """
  captures_root = tree.traveller_captures
  if not captures_root.is_dir():
    raise FileNotFoundError(f'no traveller capture root at {captures_root}')

  stored: list[PurePosixPath] = []
  issues = []
  for site_directory in sorted(
    path for path in captures_root.iterdir() if path.is_dir()
  ):
    site = site_directory.name

    for capture in _captures_in(site_directory):
      relative_to_root = PurePosixPath(capture.relative_to(captures_root))
      record = tree.traveller_records / f'{relative_to_root}.json'

      parse = _parser_for(site, capture.suffix)
      if not parse:
        issues.append(
          _UNRECOGNIZED_CAPTURE.issue(f'no parser reads {relative_to_root}')
        )
        continue

      if not refresh and _is_current(record, capture):
        continue

      # TODO: decode by the charset a capture declares rather than assuming
      # UTF-8. Every capture on hand reads clean, and one that did not would
      # raise rather than mislead, so this waits on a capture that exercises it.
      recorded_url = capture_urls.read_url(capture)
      issues.extend(recorded_url.issues)
      traveller = parse(
        capture.read_text(),
        reference=CaptureReference(
          path=str(relative_to_root), url=recorded_url.value
        ),
      )
      if not traveller.boards:
        issues.append(
          _CAPTURE_HELD_NO_BOARDS.issue(
            f'{relative_to_root} parsed as {traveller.source} but holds no '
            f'boards, so nothing was stored for it: {traveller.event!r}'
          )
        )
        continue

      record.parent.mkdir(parents=True, exist_ok=True)
      record.write_text(traveller.model_dump_json(indent=2) + '\n')
      stored.append(relative_to_root)

  return issue_reporting.Read(tuple(stored), tuple(issues))
