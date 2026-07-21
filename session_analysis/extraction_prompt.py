# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The system prompt that scopes the vision model to transcription.

Passed to `vision_model_invocation.invoke_vision_model` as `system_prompt`,
replacing the CLI's default agentic-coding prompt entirely. The prompt text
itself lives in `extraction_prompt.md` — plain prose, not code — and is loaded
here as a string. See models.md (Vision model output) for the output contract
the prompt targets, and spec.md (Extraction) for why the job is scoped this
narrowly.
"""

import pathlib

VISION_MODEL_SYSTEM_PROMPT: str = (
  pathlib.Path(__file__).parent / 'extraction_prompt.md'
).read_text()

# The user-turn text closing the request, after the last image part. Prompt
# content, kept here with the rest of the prompt rather than baked into the
# request plumbing.
TRANSCRIPTION_INSTRUCTION = 'Transcribe the attached scan.'
