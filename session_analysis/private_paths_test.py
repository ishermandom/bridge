# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for this project's private data layout, and for finding it.

Locating the checkout is injected rather than faked: git is the one dependency a
fake filesystem cannot stand in for, so `discover_private_tree` takes a
`find_checkout` callable and a test hands it a directory. Only the default
implementation goes unexercised, and it holds nothing but the git call.
"""

from pathlib import Path

import pytest

from session_analysis.private_paths import (
  PrivateTree,
  discover_private_tree,
)

_ROOT = Path('/private/session_analysis')


# --- the scoresheet images ---


def test_the_inbox_and_archive_sit_under_the_scoresheets_tree() -> None:
  tree = PrivateTree(_ROOT)

  assert tree.scan_inbox == Path('/private/session_analysis/scoresheets/inbox')
  assert tree.scan_archive == Path(
    '/private/session_analysis/scoresheets/archive'
  )


def test_a_scan_that_failed_lands_outside_the_inbox() -> None:
  """Terminal, not staging: the next run must not retry it."""
  tree = PrivateTree(_ROOT)

  assert tree.scan_failures == Path(
    '/private/session_analysis/scoresheets/failed'
  )
  assert not tree.scan_failures.is_relative_to(tree.scan_inbox)


# --- the traveller trees ---


def test_captures_and_their_records_sit_apart_under_one_directory() -> None:
  tree = PrivateTree(_ROOT)

  assert tree.traveller_captures == Path(
    '/private/session_analysis/travellers/raw'
  )
  assert tree.traveller_records == Path(
    '/private/session_analysis/travellers/parsed'
  )


# --- what the pipeline writes ---


def test_session_records_sit_apart_from_the_scans_behind_them() -> None:
  """A record outlives the staging that produced it, so it is filed apart."""
  tree = PrivateTree(_ROOT)

  assert tree.session_records == Path('/private/session_analysis/sessions')
  assert not tree.session_records.is_relative_to(tree.scan_archive)


def test_a_digitized_session_waits_below_the_reviewed_ones() -> None:
  """Review is deferred until a traveller lands, so ingest writes here."""
  tree = PrivateTree(_ROOT)

  assert tree.pending_session_records == Path(
    '/private/session_analysis/sessions/pending'
  )
  # Below `sessions`, so both are found together — but not among them, so the
  # analysis stage reading `sessions/*.json` sees only reviewed records.
  assert tree.pending_session_records.parent == tree.session_records


# --- the root as the single setting ---


def test_repointing_the_root_moves_every_tree_with_it() -> None:
  """The whole point of one setting: the trees cannot drift apart."""
  tree = PrivateTree(Path('/elsewhere'))

  for path in (
    tree.scan_inbox,
    tree.scan_archive,
    tree.scan_failures,
    tree.traveller_captures,
    tree.traveller_records,
    tree.session_records,
    tree.pending_session_records,
  ):
    assert path.is_relative_to(Path('/elsewhere'))


# --- finding the tree beside a checkout ---


def test_the_tree_is_found_beside_the_checkout(tmp_path: Path) -> None:
  (tmp_path / 'bridge').mkdir()
  (tmp_path / 'bridge-private').mkdir()

  tree = discover_private_tree(find_checkout=lambda: tmp_path / 'bridge')

  assert tree.root == tmp_path / 'bridge-private' / 'session_analysis'


def test_a_missing_private_checkout_names_where_it_was_expected(
  tmp_path: Path,
) -> None:
  (tmp_path / 'bridge').mkdir()

  with pytest.raises(FileNotFoundError, match=str(tmp_path / 'bridge-private')):
    discover_private_tree(find_checkout=lambda: tmp_path / 'bridge')
