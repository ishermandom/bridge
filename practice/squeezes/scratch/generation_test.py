# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for automatic-simple-squeeze generation."""

import random

import pytest

from engine import GameSession, SessionStatus
from generation import generate_automatic_simple_squeeze
from solver import QuantumSolver


@pytest.mark.parametrize(
  ('ending_size', 'seed'), [(3, 0), (4, 1), (5, 2), (6, 3)]
)
def test_generated_problem_plays_out_to_its_target(
  ending_size: int, seed: int
) -> None:
  generated = generate_automatic_simple_squeeze(
    random.Random(seed), ending_size
  )

  # Certification already ran inside generation; playing the hand end to end
  # exercises the engine against the generated family too.
  session = GameSession(generated.problem)
  solver = QuantumSolver(generated.problem)
  while session.status is SessionStatus.PLAYING:
    winning = solver.winning_declarer_cards(session.position)
    card = min(winning, key=lambda c: (c.rank, c.suit.value))
    session.play_declarer_card(card)

  assert session.status is SessionStatus.COMPLETE
  assert session.position.declarer_tricks == ending_size


def test_guards_sit_on_both_sides_across_the_family() -> None:
  generated = generate_automatic_simple_squeeze(random.Random(4))

  layouts = generated.problem.layouts
  assert any(generated.guard_cards <= layout.west for layout in layouts)
  assert any(generated.guard_cards <= layout.east for layout in layouts)


def test_generation_is_deterministic_for_a_seed() -> None:
  first = generate_automatic_simple_squeeze(random.Random(7), 5)
  second = generate_automatic_simple_squeeze(random.Random(7), 5)

  assert first == second


def test_different_seeds_vary_the_problem() -> None:
  first = generate_automatic_simple_squeeze(random.Random(0), 5)
  second = generate_automatic_simple_squeeze(random.Random(1), 5)

  assert first.problem != second.problem


@pytest.mark.parametrize('ending_size', [2, 7])
def test_out_of_range_ending_size_is_rejected(ending_size: int) -> None:
  with pytest.raises(ValueError, match='ending_size'):
    generate_automatic_simple_squeeze(random.Random(0), ending_size)
