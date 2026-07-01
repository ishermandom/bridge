# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the models' serialization contract.

The models are plain data holders, so most of their behaviour is Pydantic's, not
ours — constructing one and reading a field back only exercises the framework.
What is ours, and what the stored JSON depends on, is the serialization shape:
chiefly the tagged `Outcome` union, which must keep a played contract, a passout,
and an unparsed cell distinct. That is what these tests pin. Turning vision-model
strings into these models is the parser's behaviour, and is tested there.
"""

from session_analysis.enums import Direction, Penalty, Strain
from session_analysis.models import (
  Contract,
  Outcome,
  Passout,
  PlayedContract,
  Result,
)

# --- the Outcome union keeps played / passout / unparsed distinct ---


def test_played_outcome_round_trips_as_a_played_contract() -> None:
  outcome = Outcome(
    raw='4S N +6',
    resolution=PlayedContract(
      contract=Contract(
        level=4,
        strain=Strain.SPADES,
        declarer=Direction.NORTH,
        penalty=Penalty.NONE,
      ),
      result=Result(tricks_taken=12),
    ),
  )
  restored = Outcome.model_validate_json(outcome.model_dump_json())
  assert isinstance(restored.resolution, PlayedContract)
  assert restored == outcome


def test_passout_round_trips_as_a_passout() -> None:
  outcome = Outcome(raw='PASSOUT', resolution=Passout())
  restored = Outcome.model_validate_json(outcome.model_dump_json())
  assert isinstance(restored.resolution, Passout)


def test_unparsed_cell_round_trips_as_a_null_resolution() -> None:
  outcome = Outcome(raw='4?N', resolution=None)
  restored = Outcome.model_validate_json(outcome.model_dump_json())
  assert restored.resolution is None


def test_passout_and_unparsed_cell_serialize_differently() -> None:
  # The point of the tagged union: these two must not collapse to the same JSON.
  passout = Outcome(raw='PASSOUT', resolution=Passout()).model_dump(mode='json')
  unparsed = Outcome(raw='4?N', resolution=None).model_dump(mode='json')
  assert passout['resolution'] == {'kind': 'passout'}
  assert unparsed['resolution'] is None
