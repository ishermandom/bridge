# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The shared frozen base for the project's pydantic models.

Both the canonical models (`models`) and the transient vision-model input
(`assembly`) build on this, so immutability is one decision in one place rather
than a config repeated per model.
"""

import pydantic


class FrozenModel(pydantic.BaseModel):
  """Base for the project's pydantic models: frozen, so instances are immutable.

  Freezing makes an instance immutable once built — the same data hygiene serves
  the stored canonical record and the transient vision-model input alike.
  Collection fields use `tuple` rather than `list` so the immutability is deep,
  not just a block on reassigning the field.
  """

  model_config = pydantic.ConfigDict(frozen=True)
