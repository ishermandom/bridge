# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the sidecar recording where each capture was fetched from."""

from pathlib import Path

from session_analysis import capture_urls

_URL = 'https://paloaltobridge.org/gameresults2/vi/D260714A.pbn'


def _put_sidecar(capture: Path, url: str) -> None:
  """Put a sidecar on disk the way a fetcher's own writer would."""
  sidecar = capture_urls.sidecar_for(capture)
  sidecar.parent.mkdir(parents=True, exist_ok=True)
  sidecar.write_bytes(capture_urls.sidecar_contents(url))


# --- where a sidecar sits ---


def test_the_sidecar_sits_beside_the_capture(tmp_path: Path) -> None:
  capture = tmp_path / 'vi' / 'D260714A.pbn'

  assert capture_urls.sidecar_for(capture) == (
    tmp_path / 'vi' / 'D260714A.pbn.url'
  )


def test_captures_differing_only_by_extension_keep_separate_sidecars(
  tmp_path: Path,
) -> None:
  """The club publishes a PBN and an HTML per game, often alike in stem."""
  deal = capture_urls.sidecar_for(tmp_path / 'D260714A.pbn')
  recap = capture_urls.sidecar_for(tmp_path / 'D260714A.htm')

  assert deal != recap


# --- writing and reading back ---


def test_a_recorded_capture_reads_back_with_its_url(tmp_path: Path) -> None:
  capture = tmp_path / 'D260714A.pbn'
  _put_sidecar(capture, _URL)

  assert capture_urls.read_url(capture).value == _URL


def test_a_sidecar_holds_the_url_as_one_line(tmp_path: Path) -> None:
  assert capture_urls.sidecar_contents(_URL) == f'{_URL}\n'.encode()


def test_re_fetching_a_capture_replaces_its_url(tmp_path: Path) -> None:
  capture = tmp_path / 'D260714A.pbn'

  _put_sidecar(capture, 'https://paloaltobridge.org/old.pbn')
  _put_sidecar(capture, _URL)

  assert capture_urls.read_url(capture).value == _URL


# --- a capture nothing recorded a URL for ---


def test_a_capture_with_no_sidecar_has_no_url(tmp_path: Path) -> None:
  """A hand-saved capture never had one, and none is guessed from the path."""
  assert capture_urls.read_url(tmp_path / 'R260629M.html').value is None


# --- a sidecar something else wrote ---


def test_an_empty_sidecar_costs_the_url_and_not_the_run(
  tmp_path: Path,
) -> None:
  """Only `sidecar_contents` writes these, so an empty one is someone else."""
  capture = tmp_path / 'D260714A.pbn'
  capture_urls.sidecar_for(capture).write_text('   \n')

  read = capture_urls.read_url(capture)

  assert read.value is None
  assert [issue.code for issue in read.issues] == ['unreadable_sidecar']
  assert 'D260714A.pbn.url' in read.issues[0].message
