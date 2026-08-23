# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the notations ACBL's club and tournament pages share."""

import pytest

from session_analysis.acbl_notation import (
  AcblNotationError,
  double_dummy_tricks,
  par,
  player_name,
)
from session_analysis.enums import Direction, Penalty, Strain
from session_analysis.models import PlayedContract

# A double-dummy table with a count in every cell, for the par tests that need
# one to be there but do not turn on what it holds. `par` takes a table because
# it recovers the result ACBL omits from a contract that makes exactly; a table
# with holes would leave these tests resting on which cells were filled.
COMPLETE_TRICK_TABLE = double_dummy_tricks(
  north_south='NS: 4S 4H 4D 4C 4NT', east_west='EW: 3S 3H 3D 3C 3NT'
)


def played(resolution: object) -> PlayedContract:
  """Narrow a resolution to the played contract the test expects it to be."""
  assert isinstance(resolution, PlayedContract)
  return resolution


# --- the two forms of a double-dummy cell ---


def test_a_level_is_six_tricks_fewer_than_the_count() -> None:
  # `4S` names a makeable contract, so it is ten tricks and not four.
  tricks = double_dummy_tricks(
    north_south='NS: 4S 1H 1D 1C 1NT', east_west='EW: 1S 1H 1D 1C 1NT'
  )
  assert tricks[Direction.NORTH][Strain.SPADES] == 10


def test_a_trailing_number_is_the_trick_count_itself() -> None:
  # `S5` is the count, which ACBL switches to below seven tricks — where there
  # is no makeable contract to name.
  tricks = double_dummy_tricks(
    north_south='NS: S5 H0 D1 C6 NT2', east_west='EW: 1S 1H 1D 1C 1NT'
  )
  assert tricks[Direction.NORTH][Strain.SPADES] == 5
  assert tricks[Direction.NORTH][Strain.HEARTS] == 0


def test_one_cell_covers_both_seats_of_its_side() -> None:
  # `4S` is written once and answers for North and South alike.
  tricks = double_dummy_tricks(
    north_south='NS: 4S 1H 1D 1C 1NT', east_west='EW: 1S 1H 1D 1C 1NT'
  )
  assert tricks[Direction.NORTH][Strain.SPADES] == 10
  assert tricks[Direction.SOUTH][Strain.SPADES] == 10


def test_a_slash_splits_the_two_seats_in_the_order_the_side_names_them() -> (
  None
):
  # `3/4D` under NS is North three and South four; under EW it is East then
  # West.
  tricks = double_dummy_tricks(
    north_south='NS: 1S 1H 3/4D 1C 1NT', east_west='EW: 1S 1H 5/6D 1C 1NT'
  )
  assert tricks[Direction.NORTH][Strain.DIAMONDS] == 9
  assert tricks[Direction.SOUTH][Strain.DIAMONDS] == 10
  assert tricks[Direction.EAST][Strain.DIAMONDS] == 11
  assert tricks[Direction.WEST][Strain.DIAMONDS] == 12


def test_seats_straddling_seven_tricks_are_stated_twice() -> None:
  # When one seat makes a contract and the other does not, ACBL prints the
  # strain in both forms: `1/-S` for the pair of levels, then `S7/6` for the
  # counts. The counts are what survive.
  tricks = double_dummy_tricks(
    north_south='NS: 1S 1H 1D 1C 1NT',
    east_west='EW: 1C 2D 1/-S H4 S7/6 NT5',
  )
  assert tricks[Direction.EAST][Strain.SPADES] == 7
  assert tricks[Direction.WEST][Strain.SPADES] == 6


def test_a_dash_alone_leaves_the_trick_count_unstated() -> None:
  # The dash says only "fewer than seven", so `None` is the honest reading when
  # nothing else states the count.
  tricks = double_dummy_tricks(
    north_south='NS: 1H 1D 1C 1NT', east_west='EW: 1/-S 1H 1D 1C 1NT'
  )
  assert tricks[Direction.EAST][Strain.SPADES] == 7
  assert tricks[Direction.WEST][Strain.SPADES] is None


def test_a_strain_no_cell_names_leaves_its_trick_count_unstated() -> None:
  tricks = double_dummy_tricks(north_south='NS: 4S', east_west='EW: 3H')
  assert tricks[Direction.NORTH][Strain.CLUBS] is None


def test_notrump_spelled_with_a_bare_n() -> None:
  # Every captured page writes notrump `NT`, but a bare `N` can only mean the
  # same thing, so it is read rather than reported as an unreadable cell.
  tricks = double_dummy_tricks(north_south='NS: 3N', east_west='EW: N4')

  assert tricks[Direction.NORTH][Strain.NOTRUMP] == 9
  assert tricks[Direction.EAST][Strain.NOTRUMP] == 4


def test_whitespace_scattered_by_the_rendered_page_is_ignored() -> None:
  # A tournament page builds a line out of nested elements, so flattening it
  # leaves spaces inside cells that the club's own data has none of.
  scattered = double_dummy_tricks(
    north_south='NS: 2/ 3 D 5 H 2NT C 5 S 6', east_west='EW: 1S 1H 1D 1C 1NT'
  )
  compact = double_dummy_tricks(
    north_south='NS: 2/3D 5H 2NT C5 S6', east_west='EW: 1S 1H 1D 1C 1NT'
  )
  assert scattered == compact


def test_an_unreadable_cell_is_refused() -> None:
  with pytest.raises(AcblNotationError, match='ZZ'):
    double_dummy_tricks(north_south='NS: 4S ZZ', east_west='EW: 1S')


# --- par ---


def test_par_stated_for_a_side_expands_to_both_seats() -> None:
  parsed = par('Par: -1510 7S-EW', double_dummy_tricks=COMPLETE_TRICK_TABLE)
  assert parsed is not None
  assert parsed.score == -1510
  assert [
    played(contract).contract.declarer for contract in parsed.resolutions
  ] == [
    Direction.EAST,
    Direction.WEST,
  ]


def test_par_stated_for_a_seat() -> None:
  parsed = par('Par: 460 3NT-S+2', double_dummy_tricks=COMPLETE_TRICK_TABLE)
  assert parsed is not None
  assert played(parsed.resolutions[0]).contract.declarer == Direction.SOUTH
  assert played(parsed.resolutions[0]).result.tricks_taken == 11


def test_a_doubled_par_sacrifice() -> None:
  parsed = par('Par: -800 7H*-NS-4', double_dummy_tricks=COMPLETE_TRICK_TABLE)
  assert parsed is not None
  assert played(parsed.resolutions[0]).contract.penalty == Penalty.DOUBLED
  assert played(parsed.resolutions[0]).result.tricks_taken == 9


def test_several_par_contracts_share_one_score() -> None:
  parsed = par(
    'Par: -450 4S-EW+1/4H-EW+1', double_dummy_tricks=COMPLETE_TRICK_TABLE
  )
  assert parsed is not None
  # Two contracts, each expanded across its side's two seats.
  assert len(parsed.resolutions) == 4


def test_par_with_no_label_of_its_own() -> None:
  # The two surfaces label par differently and in different places: the club
  # blob writes `Par:` inline, while a tournament page prints `Par Score` in a
  # link beside the value. Reading the label as optional is what lets both hand
  # over what they have, rather than one of them fabricating the other's
  # spelling to satisfy the pattern.
  parsed = par('+450 5H-NS', double_dummy_tricks=COMPLETE_TRICK_TABLE)
  assert parsed is not None
  assert parsed.score == 450


def test_a_result_ACBL_omits_is_recovered_from_the_table() -> None:
  # ACBL writes no marker when par makes exactly, so the trick count comes from
  # declarer's makeable tricks in the strain — `4S` for North, which is ten.
  tricks = double_dummy_tricks(
    north_south='NS: 4S 4H 4D 4C 4NT', east_west='EW: 3S 3H 3D 3C 3NT'
  )

  parsed = par('Par: 420 4S-N', double_dummy_tricks=tricks)
  assert parsed is not None
  assert played(parsed.resolutions[0]).result.tricks_taken == 10


def test_a_page_stating_no_par() -> None:
  assert par('', double_dummy_tricks=COMPLETE_TRICK_TABLE) is None


def test_an_unreadable_par_contract_is_refused() -> None:
  with pytest.raises(AcblNotationError, match='par contract'):
    par('Par: 420 nonsense', double_dummy_tricks=COMPLETE_TRICK_TABLE)


def test_a_result_no_table_can_recover_is_refused_in_this_modules_terms() -> (
  None
):
  # Recovery reaches into `notation`, whose own error type is a sibling of this
  # module's rather than a parent — so a caller catching what this function
  # documents would not catch it unless it arrives re-raised.
  with pytest.raises(AcblNotationError, match='states no result'):
    par('Par: 420 4S-N', double_dummy_tricks=None)


# --- player names ---


def test_a_name_written_surname_first_is_turned_around() -> None:
  # ACBL is the only source that writes a name this way round; comparing two
  # captures of one session means agreeing on the order first.
  assert player_name('Alfa, Ann') == 'Ann Alfa'


def test_a_name_already_given_name_first_is_left_alone() -> None:
  # The comma is what marks ACBL's order, so a name without one is already the
  # way a traveller keeps it.
  assert player_name('Ann Alfa') == 'Ann Alfa'
