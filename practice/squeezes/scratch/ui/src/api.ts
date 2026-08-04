// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Typed client for the FastAPI backend (../../server.py). The Vite dev
// server proxies `/api` to localhost:8642, so paths stay origin-relative.

export interface SeatCard {
  seat: string;
  card: string;
}

export interface Trick {
  plays: SeatCard[];
  winner: string;
}

export interface DefenderLayout {
  west: string[];
  east: string[];
}

export interface PlayError {
  played: string;
  message: string;
  witnesses: DefenderLayout[];
}

export type GameStatus = 'playing' | 'failed' | 'complete';

export interface GameView {
  game_id: string;
  north: string[];
  south: string[];
  west_count: number;
  east_count: number;
  current_trick: SeatCard[];
  completed_tricks: Trick[];
  declarer_tricks: number;
  target_tricks: number;
  seat_to_play: string | null;
  legal_cards: string[];
  status: GameStatus;
  error: PlayError | null;
  summary: string | null;
}

async function postJson(path: string, body: unknown): Promise<GameView> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${response.status} from ${path}: ${await response.text()}`);
  }
  return (await response.json()) as GameView;
}

export function newGame(endingSize: number): Promise<GameView> {
  return postJson('/api/games', { ending_size: endingSize });
}

export function playCard(gameId: string, card: string): Promise<GameView> {
  return postJson(`/api/games/${gameId}/plays`, { card });
}

export function restartGame(gameId: string): Promise<GameView> {
  return postJson(`/api/games/${gameId}/restart`, {});
}
