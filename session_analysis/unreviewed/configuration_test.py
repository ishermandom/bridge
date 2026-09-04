# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the settings naming the person the pipeline is run by.

The parsing tests hand `read_configuration` an in-memory stream, so most of
these write nothing; only the two covering how the file is found in a tree reach
the disk.
"""

import io
from pathlib import Path

import pytest

from session_analysis.private_paths import PrivateTree
from session_analysis.unreviewed.configuration import (
  Configuration,
  ConfigurationError,
  load_configuration,
  read_configuration,
)


def _read(text: str) -> Configuration:
  """Parse a configuration from text, as `load_configuration` reads a file."""
  return read_configuration(io.BytesIO(text.encode()))


# --- reading a configuration ---


def test_every_setting_reaches_the_configuration() -> None:
  configuration = _read(
    'player_name = "First Last"\nacbl_player_number = "0000000"\n'
  )

  assert configuration.player_name == 'First Last'
  assert configuration.acbl_player_number == '0000000'


def test_a_player_number_keeps_its_leading_zeros() -> None:
  # Quoted in the file and a string in the model: it is an identifier, and
  # reading it as a number would drop the zeros it starts with.
  configuration = _read(
    'player_name = "First Last"\nacbl_player_number = "0001234"\n'
  )

  assert configuration.acbl_player_number == '0001234'


# --- a configuration that cannot be used ---


def test_a_missing_setting_is_named() -> None:
  with pytest.raises(ConfigurationError) as raised:
    _read('player_name = "First Last"\n')

  assert 'acbl_player_number' in str(raised.value)


def test_a_setting_written_the_wrong_way_is_not_called_missing() -> None:
  # A player number left unquoted is a number in TOML. Its writer can see the
  # key sitting there, so being told it is absent sends them looking for
  # nothing.
  with pytest.raises(ConfigurationError) as raised:
    _read('player_name = "First Last"\nacbl_player_number = 1234\n')

  assert 'cannot use acbl_player_number' in str(raised.value)
  assert 'states no' not in str(raised.value)


def test_a_file_that_is_not_toml_at_all_is_reported_as_such() -> None:
  with pytest.raises(ConfigurationError, match='not valid TOML'):
    _read('player_name: First Last\n')


def test_a_file_in_another_encoding_is_reported_not_raised() -> None:
  # An accented name typed into an editor that still writes Latin-1. TOML is
  # UTF-8 by definition, so this fails before the parse — and it is a fault the
  # command tells its reader about, not one it lets out as a traceback.
  with pytest.raises(ConfigurationError, match='UTF-8'):
    read_configuration(
      io.BytesIO('player_name = "First Lást"\n'.encode('latin-1'))
    )


def test_a_setting_left_blank_is_not_taken_as_supplied() -> None:
  # The shape a half-filled template takes. Left to stand, an empty name would
  # match no row in any traveller and report itself as a session that never
  # names us, far from the file that is actually unfinished.
  with pytest.raises(ConfigurationError) as raised:
    _read('player_name = ""\nacbl_player_number = "0000000"\n')

  assert 'cannot use player_name' in str(raised.value)


# --- finding the file in a tree ---


def test_the_configuration_is_read_from_the_tree_it_accompanies(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)
  tree.configuration_file.write_text(
    'player_name = "First Last"\nacbl_player_number = "0000000"\n'
  )

  assert load_configuration(tree).player_name == 'First Last'


def test_a_tree_with_no_configuration_says_where_one_belongs(
  tmp_path: Path,
) -> None:
  # The first run on a new machine, where the message has to do the work of
  # telling someone what to go and write.
  tree = PrivateTree(tmp_path)

  with pytest.raises(ConfigurationError) as raised:
    load_configuration(tree)

  assert str(tree.configuration_file) in str(raised.value)
  assert 'player_name' in str(raised.value)
