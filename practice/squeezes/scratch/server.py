# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""HTTP surface for the squeeze trainer.

A thin FastAPI layer over `engine.GameSession`: deal a certified problem, play
declarer cards, restart. Sessions live in process memory — this is a single-user
local tool. Run from this directory:

```sh
uv run --project ../../.. uvicorn server:app --port 8642
```

The React dev server under `ui/` proxies `/api` here.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Iterable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cards import SUITS_HIGH_TO_LOW, Card
from engine import ErrorReport, GameSession, SessionStatus
from generation import GeneratedProblem, generate_automatic_simple_squeeze
from problems import Layout


class SeatCardView(BaseModel):
  """One card played by one seat, in wire notation (`S`/`SA`)."""

  seat: str
  card: str


class TrickView(BaseModel):
  """A completed trick with its winner."""

  plays: list[SeatCardView]
  winner: str


class LayoutView(BaseModel):
  """A defender layout, shown when explaining an error."""

  west: list[str]
  east: list[str]


class ErrorView(BaseModel):
  """Why the hand froze: the fatal card and the layouts that beat it."""

  played: str
  message: str
  witnesses: list[LayoutView]


class DealView(BaseModel):
  """The original deal, revealed once the hand is over.

  `layouts` holds the defender layouts still consistent with the play — exactly
  one after a completed hand, possibly several after a mid-hand freeze.
  """

  north: list[str]
  south: list[str]
  layouts: list[LayoutView]


class GameView(BaseModel):
  """Everything the UI needs to render a game."""

  game_id: str
  north: list[str]
  south: list[str]
  west_count: int
  east_count: int
  current_trick: list[SeatCardView]
  completed_tricks: list[TrickView]
  declarer_tricks: int
  target_tricks: int
  seat_to_play: str | None
  legal_cards: list[str]
  status: str
  error: ErrorView | None
  # Teaching notes and the full deal; revealed only once the hand is over, so
  # they can't tip off the technique mid-play.
  summary: str | None
  deal: DealView | None


class NewGameRequest(BaseModel):
  """Options for dealing a fresh problem."""

  ending_size: int = Field(default=5, ge=3, le=6)
  seed: int | None = None


class PlayRequest(BaseModel):
  """One declarer card to play, in `SA` notation."""

  card: str


class _ActiveGame:
  """A live session plus the teaching metadata of its problem."""

  def __init__(self, session: GameSession, generated: GeneratedProblem) -> None:
    self.session = session
    self.generated = generated


def create_app() -> FastAPI:
  """Build the API with its own in-memory session store."""
  app = FastAPI(title='Squeeze trainer')
  games: dict[str, _ActiveGame] = {}

  def find_game(game_id: str) -> _ActiveGame:
    """The active game for `game_id`, or a 404."""
    try:
      return games[game_id]
    except KeyError:
      raise HTTPException(
        status_code=404, detail=f'no such game: {game_id}'
      ) from None

  @app.post('/api/games')
  def new_game(request: NewGameRequest) -> GameView:
    """Deal a certified problem and start a session on it."""
    rng = random.Random(request.seed)
    generated = generate_automatic_simple_squeeze(rng, request.ending_size)
    game_id = uuid.uuid4().hex[:8]
    games[game_id] = _ActiveGame(GameSession(generated.problem), generated)
    return _game_view(game_id, games[game_id])

  @app.get('/api/games/{game_id}')
  def get_game(game_id: str) -> GameView:
    """The current state of a game."""
    return _game_view(game_id, find_game(game_id))

  @app.post('/api/games/{game_id}/plays')
  def play_card(game_id: str, request: PlayRequest) -> GameView:
    """Play one declarer-side card; the defenders answer in the same call."""
    active = find_game(game_id)
    try:
      card = Card.from_code(request.card)
    except ValueError as error:
      raise HTTPException(status_code=422, detail=str(error)) from error
    try:
      active.session.play_declarer_card(card)
    except (ValueError, RuntimeError) as error:
      # An illegal card or an out-of-turn play; the message says which.
      raise HTTPException(status_code=400, detail=str(error)) from error
    return _game_view(game_id, active)

  @app.post('/api/games/{game_id}/restart')
  def restart_game(game_id: str) -> GameView:
    """Reset the same problem to its starting position."""
    active = find_game(game_id)
    active.session.restart()
    return _game_view(game_id, active)

  return app


def _codes(cards: Iterable[Card]) -> list[str]:
  """Card codes in display order: ♠♥♦♣, high to low within a suit."""
  ordered = sorted(
    cards, key=lambda c: (SUITS_HIGH_TO_LOW.index(c.suit), -c.rank)
  )
  return [card.code for card in ordered]


def _layout_views(layouts: Iterable[Layout]) -> list[LayoutView]:
  """Project defender layouts into the wire format."""
  return [
    LayoutView(west=_codes(layout.west), east=_codes(layout.east))
    for layout in layouts
  ]


def _error_view(report: ErrorReport) -> ErrorView:
  """Project an engine error report into the wire format."""
  return ErrorView(
    played=report.played.code,
    message=report.message,
    witnesses=_layout_views(report.witnesses),
  )


def _game_view(game_id: str, active: _ActiveGame) -> GameView:
  """Project a session into the wire format."""
  session = active.session
  position = session.position
  seat = session.seat_to_play()
  hand_size = len(session.problem.north)
  is_over = session.status is not SessionStatus.PLAYING
  return GameView(
    game_id=game_id,
    north=_codes(position.north),
    south=_codes(position.south),
    west_count=hand_size - len(position.west_played),
    east_count=hand_size - len(position.east_played),
    current_trick=[
      SeatCardView(seat=seat_played.value, card=card.code)
      for seat_played, card in position.trick
    ],
    completed_tricks=[
      TrickView(
        plays=[
          SeatCardView(seat=seat_played.value, card=card.code)
          for seat_played, card in trick.plays
        ],
        winner=trick.winner.value,
      )
      for trick in session.completed_tricks
    ],
    declarer_tricks=position.declarer_tricks,
    target_tricks=session.problem.target_tricks,
    seat_to_play=seat.value if seat else None,
    legal_cards=_codes(session.legal_cards()),
    status=session.status.value,
    error=_error_view(session.error) if session.error else None,
    summary=active.generated.summary if is_over else None,
    deal=DealView(
      north=_codes(session.problem.north),
      south=_codes(session.problem.south),
      layouts=_layout_views(session.surviving_layouts()),
    )
    if is_over
    else None,
  )


app = create_app()
