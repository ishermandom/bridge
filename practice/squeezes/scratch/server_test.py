# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the HTTP surface."""

from fastapi.testclient import TestClient

from server import create_app


def _make_client() -> TestClient:
  return TestClient(create_app())


def _new_game(client: TestClient) -> dict[str, object]:
  """Deal a small deterministic game and return its view."""
  response = client.post(
    '/api/games', json={'ending_size': 3, 'seed': 0}
  )
  assert response.status_code == 200
  view: dict[str, object] = response.json()
  return view


def test_new_game_deals_a_playable_position() -> None:
  view = _new_game(_make_client())

  south = view['south']
  north = view['north']
  legal = view['legal_cards']
  assert isinstance(south, list)
  assert isinstance(north, list)
  assert isinstance(legal, list)

  assert view['status'] == 'playing'
  assert view['seat_to_play'] == 'S'
  assert len(south) == 3
  assert len(north) == 3
  assert view['west_count'] == 3
  # South is on lead, so the whole hand is legal.
  assert sorted(legal) == sorted(south)
  # Teaching notes stay hidden while the hand is live.
  assert view['summary'] is None


def test_playing_a_legal_card_advances_the_game() -> None:
  client = _make_client()
  view = _new_game(client)
  legal = view['legal_cards']
  assert isinstance(legal, list)

  response = client.post(
    f'/api/games/{view["game_id"]}/plays', json={'card': legal[0]}
  )

  assert response.status_code == 200
  # South's card left the hand, whatever the defenders then did.
  assert len(response.json()['south']) == 2


def test_malformed_card_code_is_rejected() -> None:
  client = _make_client()
  view = _new_game(client)

  response = client.post(
    f'/api/games/{view["game_id"]}/plays', json={'card': 'ZZ'}
  )

  assert response.status_code == 422
  assert 'card code' in response.json()['detail']


def test_card_outside_the_hand_is_rejected() -> None:
  client = _make_client()
  view = _new_game(client)
  legal = view['legal_cards']
  assert isinstance(legal, list)
  outside = next(
    code
    for suit in 'SHDC'
    for rank in 'AKQJT98765432'
    if (code := suit + rank) not in legal
  )

  response = client.post(
    f'/api/games/{view["game_id"]}/plays', json={'card': outside}
  )

  assert response.status_code == 400
  assert 'not a legal play' in response.json()['detail']


def test_unknown_game_is_a_404() -> None:
  response = _make_client().get('/api/games/nope')

  assert response.status_code == 404


def test_restart_resets_the_board() -> None:
  client = _make_client()
  view = _new_game(client)
  legal = view['legal_cards']
  assert isinstance(legal, list)
  client.post(f'/api/games/{view["game_id"]}/plays', json={'card': legal[0]})

  response = client.post(f'/api/games/{view["game_id"]}/restart')

  assert response.status_code == 200
  restarted = response.json()
  assert restarted['status'] == 'playing'
  assert restarted['completed_tricks'] == []
  assert len(restarted['south']) == 3
