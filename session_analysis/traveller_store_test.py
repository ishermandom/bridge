# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for turning the captures on disk into stored travellers.

The captures are the committed placeholder-name fixtures the parser tests use.
What is under test here is the filing — which parser a capture's directory and
extension pick, where a record lands, and what provenance it carries — not the
parsing, which each parser's own tests cover.

Every decision about a capture's content is tested by handing `parse_captures`
the capture in memory. Only the tests of walking the tree, comparing timestamps,
reading sidecars, and writing records put captures on disk, in a temporary
capture root.
"""

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import pytest

from session_analysis import capture_urls
from session_analysis.enums import Direction, Rank, Strain, Suit
from session_analysis.models import Card, Deal, Hand
from session_analysis.private_paths import (
  ACBL_CLUB_CAPTURE_DIRECTORY,
  ACBL_TOURNAMENT_CAPTURE_DIRECTORY,
  CLUB_CAPTURE_DIRECTORY,
  PrivateTree,
)
from session_analysis.testing.deals import a_suit_to_each_seat, whole_suit
from session_analysis.traveller_store import (
  Capture,
  parse_captures,
  store_travellers,
)
from session_analysis.travellers import (
  DoubleDummyTricks,
  Traveller,
  TravellerSource,
)

TESTDATA = Path(__file__).parent / 'testdata/travellers'

_CLUB_PBN = f'{CLUB_CAPTURE_DIRECTORY}/gameresults2/vi/D260714A.pbn'
_CLUB_HTML = f'{CLUB_CAPTURE_DIRECTORY}/gameresults2/vi/R260714A.htm'
_ACBL_CLUB = f'{ACBL_CLUB_CAPTURE_DIRECTORY}/my.acbl.org/details/1441256.html'
_ACBL_TOURNAMENT = (
  f'{ACBL_TOURNAMENT_CAPTURE_DIRECTORY}/live.acbl.org/1/summary.html'
)


def _put_sidecar(capture: Path, url: str) -> None:
  """Put a URL sidecar beside a capture, as a fetcher's writer would."""
  sidecar = capture_urls.sidecar_for(capture)
  sidecar.parent.mkdir(parents=True, exist_ok=True)
  sidecar.write_bytes(capture_urls.sidecar_contents(url))


def _stored_traveller(tree: PrivateTree, capture: str) -> Traveller:
  """The record a run wrote for a capture, read back from disk."""
  record = tree.traveller_records / f'{capture}.json'
  return Traveller.model_validate_json(record.read_text())


def _fixture(name: str) -> str:
  """One committed capture fixture's whole text."""
  return (TESTDATA / name).read_text()


def _tree_holding(tmp_path: Path, captures: Mapping[str, str]) -> PrivateTree:
  """A private tree whose capture root holds `captures`.

  Keys are paths relative to the capture root, so each one starts with the site
  directory the store dispatches on; values are the file contents.
  """
  tree = PrivateTree(tmp_path)
  for relative_path, contents in captures.items():
    capture = tree.traveller_captures / relative_path
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_text(contents)
  return tree


def _make_captures(
  captures: Mapping[str, str],
) -> Mapping[PurePosixPath, Capture]:
  """Captures as `parse_captures` takes them, from each one's path and text."""
  return {
    PurePosixPath(path): Capture(text.encode())
    for path, text in captures.items()
  }


def _one_capture_tree(tmp_path: Path) -> PrivateTree:
  """A tree holding a single ACBL club capture, for the provenance tests."""
  return _tree_holding(tmp_path, {_ACBL_CLUB: _fixture('acbl_club_game.html')})


# --- which parser reads a capture ---


def test_every_site_and_format_reaches_its_own_parser() -> None:
  captures = _make_captures(
    {
      _CLUB_PBN: _fixture('club_game.pbn'),
      _CLUB_HTML: _fixture('club_game_r.htm'),
      _ACBL_CLUB: _fixture('acbl_club_game.html'),
      _ACBL_TOURNAMENT: _fixture('acbl_tournament_session.html'),
    }
  )

  parsed = parse_captures(captures)

  assert {
    str(path): traveller.source for path, traveller in parsed.value.items()
  } == {
    _CLUB_PBN: TravellerSource.CLUB_PBN,
    _CLUB_HTML: TravellerSource.CLUB_HTML,
    _ACBL_CLUB: TravellerSource.ACBL_CLUB,
    _ACBL_TOURNAMENT: TravellerSource.ACBL_TOURNAMENT,
  }


def test_the_clubs_two_formats_are_told_apart_by_extension() -> None:
  """Both sit in one directory, because the club publishes both per game."""
  captures = _make_captures(
    {
      _CLUB_PBN: _fixture('club_game.pbn'),
      _CLUB_HTML: _fixture('club_game_r.htm'),
    }
  )

  parsed = parse_captures(captures)

  assert {
    str(path): traveller.source for path, traveller in parsed.value.items()
  } == {
    _CLUB_PBN: TravellerSource.CLUB_PBN,
    _CLUB_HTML: TravellerSource.CLUB_HTML,
  }


# --- where a record lands ---


def test_a_record_mirrors_its_capture_and_keeps_the_whole_name(
  tmp_path: Path,
) -> None:
  """`.json` is appended, not substituted, so two captures cannot collide."""
  tree = _tree_holding(tmp_path, {_CLUB_PBN: _fixture('club_game.pbn')})

  store_travellers(tree)

  assert (tree.traveller_records / f'{_CLUB_PBN}.json').is_file()


# --- what a run leaves alone ---


def test_a_capture_already_stored_is_not_parsed_again(tmp_path: Path) -> None:
  tree = _one_capture_tree(tmp_path)
  store_travellers(tree)

  assert not store_travellers(tree).value


def test_a_re_fetched_capture_is_parsed_again(tmp_path: Path) -> None:
  """A capture written after its record is stale, however it got there."""
  tree = _one_capture_tree(tmp_path)
  store_travellers(tree)

  capture = tree.traveller_captures / _ACBL_CLUB
  capture.touch()

  assert list(store_travellers(tree).value) == [PurePosixPath(_ACBL_CLUB)]


def test_a_sidecar_arriving_late_makes_the_record_stale(
  tmp_path: Path,
) -> None:
  """Otherwise the record would carry no URL until the capture moved."""
  tree = _one_capture_tree(tmp_path)
  store_travellers(tree)

  _put_sidecar(
    tree.traveller_captures / _ACBL_CLUB,
    'https://my.acbl.org/club-results/details/1441256',
  )

  store_travellers(tree)

  assert _stored_traveller(tree, _ACBL_CLUB).reference.url == (
    'https://my.acbl.org/club-results/details/1441256'
  )


def test_refresh_parses_a_capture_whose_record_is_current(
  tmp_path: Path,
) -> None:
  """What a parser change calls for: nothing on disk moved, parse anyway."""
  tree = _one_capture_tree(tmp_path)
  store_travellers(tree)

  assert list(store_travellers(tree, refresh=True).value) == [
    PurePosixPath(_ACBL_CLUB)
  ]


def test_a_refreshed_record_is_byte_identical_when_nothing_changed(
  tmp_path: Path,
) -> None:
  """The diff travellers.md `#testing` calls for is empty when it should be."""
  tree = _one_capture_tree(tmp_path)
  record = tree.traveller_records / f'{_ACBL_CLUB}.json'

  store_travellers(tree)
  first = record.read_text()
  store_travellers(tree, refresh=True)

  assert record.read_text() == first


# --- the provenance a record carries ---


def test_a_record_names_its_capture_relative_to_the_capture_root(
  tmp_path: Path,
) -> None:
  tree = _one_capture_tree(tmp_path)

  store_travellers(tree)

  assert _stored_traveller(tree, _ACBL_CLUB).reference.path == _ACBL_CLUB


def test_a_fetched_captures_url_is_carried_into_its_record(
  tmp_path: Path,
) -> None:
  tree = _one_capture_tree(tmp_path)
  _put_sidecar(
    tree.traveller_captures / _ACBL_CLUB,
    'https://my.acbl.org/club-results/details/1441256',
  )

  store_travellers(tree)

  assert _stored_traveller(tree, _ACBL_CLUB).reference.url == (
    'https://my.acbl.org/club-results/details/1441256'
  )


def test_a_hand_saved_capture_carries_no_url(tmp_path: Path) -> None:
  """Nothing recorded one, and a URL guessed from the path would be wrong."""
  tree = _one_capture_tree(tmp_path)

  store_travellers(tree)

  assert _stored_traveller(tree, _ACBL_CLUB).reference.url is None


def test_the_written_record_holds_the_same_reference(tmp_path: Path) -> None:
  tree = _one_capture_tree(tmp_path)

  store_travellers(tree)

  written = json.loads(
    (tree.traveller_records / f'{_ACBL_CLUB}.json').read_text()
  )
  assert written['reference'] == {'path': _ACBL_CLUB, 'url': None}


# --- what is left alone ---


def test_an_unrecognized_file_is_reported_and_skipped(
  tmp_path: Path,
) -> None:
  hand_record = f'{CLUB_CAPTURE_DIRECTORY}/gameresults2/vi/260714A.pdf'
  tree = _tree_holding(tmp_path, {_CLUB_PBN: _fixture('club_game.pbn')})
  # A PDF's opening bytes, which do not decode as text.
  (tree.traveller_captures / hand_record).write_bytes(
    b'%PDF-1.7\n\xe2\xe3\xcf\xd3'
  )

  read = store_travellers(tree)

  assert list(read.value) == [PurePosixPath(_CLUB_PBN)]
  assert [issue.code for issue in read.issues] == ['unrecognized_capture']
  assert hand_record in read.issues[0].message


def test_a_capture_holding_no_boards_is_reported_and_skipped() -> None:
  """The saved ACBL login page, and a team game's page, both land here."""
  login_page = f'{ACBL_CLUB_CAPTURE_DIRECTORY}/my.acbl.org/details/1430431.html'

  parsed = parse_captures(_make_captures({login_page: '<html></html>'}))

  assert not parsed.value
  assert [issue.code for issue in parsed.issues] == ['capture_held_no_boards']
  assert login_page in parsed.issues[0].message


def test_a_url_sidecar_is_not_itself_read_as_a_capture(
  tmp_path: Path,
) -> None:
  tree = _one_capture_tree(tmp_path)
  _put_sidecar(
    tree.traveller_captures / _ACBL_CLUB,
    'https://my.acbl.org/club-results/details/1441256',
  )

  read = store_travellers(tree)

  assert not read.issues


def test_a_dot_file_riding_along_draws_no_complaint(tmp_path: Path) -> None:
  """`.DS_Store` turns up in these directories and is worth no issue."""
  tree = _one_capture_tree(tmp_path)
  (
    tree.traveller_captures / ACBL_CLUB_CAPTURE_DIRECTORY / '.DS_Store'
  ).write_text('')

  read = store_travellers(tree)

  assert not read.issues


def test_an_unreadable_sidecar_is_reported_but_still_stores(
  tmp_path: Path,
) -> None:
  """The capture parses fine; only its provenance is lost."""
  tree = _one_capture_tree(tmp_path)
  capture_urls.sidecar_for(tree.traveller_captures / _ACBL_CLUB).write_text(
    '  \n'
  )

  read = store_travellers(tree)

  assert list(read.value) == [PurePosixPath(_ACBL_CLUB)]
  assert [issue.code for issue in read.issues] == ['unreadable_sidecar']
  assert _stored_traveller(tree, _ACBL_CLUB).reference.url is None


def test_an_unchanged_tree_reports_nothing_at_all(tmp_path: Path) -> None:
  """Neither a record nor an issue, so a routine run is silent when clean."""
  tree = _one_capture_tree(tmp_path)
  store_travellers(tree)

  read = store_travellers(tree)

  assert not read.value
  assert not read.issues


# --- the double-dummy table solved onto each board ---


def _make_club_pbn(
  *, deal: Deal, published: DoubleDummyTricks | None = None
) -> str:
  """A one-board club PBN capture of `deal`, publishing the cells `published`."""
  # `Direction` lists the seats clockwise from North, the order `N:` promises.
  hands = ' '.join(_pbn_hand(deal.hands[seat]) for seat in Direction)
  lines = ['[Board "1"]', f'[Deal "N:{hands}"]']
  if published:
    lines.append('[OptimumResultTable "Declarer;Denomination;Result"]')
    lines.extend(
      f'{seat} {strain} {tricks}'
      for seat, row in published.items()
      for strain, tricks in row.items()
    )
  return '\n'.join(lines) + '\n'


def _pbn_hand(hand: Hand) -> str:
  """A hand as PBN writes it: spades to clubs, each suit's ranks top down."""
  return '.'.join(
    ''.join(
      rank.value
      for rank in reversed(Rank)
      if Card(rank=rank, suit=suit) in hand.cards
    )
    for suit in reversed(Suit)
  )


def test_a_board_with_a_deal_carries_the_table_its_deal_solves_to() -> None:
  # North holds every spade, so North declaring spades takes all thirteen tricks
  # and East declaring them takes none.
  capture = _make_club_pbn(deal=a_suit_to_each_seat())

  parsed = parse_captures(_make_captures({_CLUB_PBN: capture}))

  [traveller] = parsed.value.values()
  table = traveller.boards[0].solved_double_dummy_tricks
  assert table
  assert table[Direction.NORTH][Strain.SPADES] == 13
  assert table[Direction.EAST][Strain.SPADES] == 0


def test_a_published_cell_the_deal_bears_out_draws_no_report() -> None:
  # North holds every spade, so takes all thirteen tricks in spades.
  capture = _make_club_pbn(
    deal=a_suit_to_each_seat(),
    published={Direction.NORTH: {Strain.SPADES: 13}},
  )

  parsed = parse_captures(_make_captures({_CLUB_PBN: capture}))

  assert not parsed.issues


def test_a_club_recaps_blank_cells_contradict_nothing() -> None:
  # The club's HTML leaves every cell below seven tricks blank, and each of this
  # recap's deals has such cells.
  captures = _make_captures({_CLUB_HTML: _fixture('club_game_r.htm')})

  parsed = parse_captures(captures)

  assert not parsed.issues


def test_a_published_cell_the_deal_contradicts_is_reported() -> None:
  # North holds every spade, so takes thirteen tricks in spades, not twelve.
  capture = _make_club_pbn(
    deal=a_suit_to_each_seat(),
    published={Direction.NORTH: {Strain.SPADES: 12}},
  )

  parsed = parse_captures(_make_captures({_CLUB_PBN: capture}))

  assert [issue.code for issue in parsed.issues] == [
    'published_double_dummy_disagrees'
  ]
  assert 'north in spades published 12, solved 13' in parsed.issues[0].message


def test_a_contradicted_cell_is_also_kept_on_its_board() -> None:
  """The record keeps the report after the run that printed it is over."""
  # North holds every spade, so takes thirteen tricks in spades, not twelve.
  capture = _make_club_pbn(
    deal=a_suit_to_each_seat(),
    published={Direction.NORTH: {Strain.SPADES: 12}},
  )

  parsed = parse_captures(_make_captures({_CLUB_PBN: capture}))

  [traveller] = parsed.value.values()
  assert [issue.code for issue in traveller.boards[0].issues] == [
    'published_double_dummy_disagrees'
  ]


def test_a_malformed_deal_goes_unsolved_and_unreported() -> None:
  """Reconciliation reports the deal itself; here it simply goes unsolved."""
  # North is short the two of spades, which no hand holds.
  short_of_a_spade = Hand(
    cards=tuple(
      card for card in whole_suit(Suit.SPADES).cards if card.rank != Rank.TWO
    )
  )
  capture = _make_club_pbn(
    deal=Deal(
      hands={**a_suit_to_each_seat().hands, Direction.NORTH: short_of_a_spade}
    )
  )

  parsed = parse_captures(_make_captures({_CLUB_PBN: capture}))

  [traveller] = parsed.value.values()
  assert traveller.boards[0].deal
  assert traveller.boards[0].solved_double_dummy_tricks is None
  assert not parsed.issues


# --- a tree that is not there ---


def test_a_missing_capture_root_is_reported_with_its_path(
  tmp_path: Path,
) -> None:
  tree = PrivateTree(tmp_path)

  with pytest.raises(FileNotFoundError, match=str(tree.traveller_captures)):
    store_travellers(tree)
