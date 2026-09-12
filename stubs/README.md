# Local type stubs

Some dependencies ship no type information, and the repo holds Python to mypy's
strict mode, so each subdirectory here is a minimal stub-only package (typing
spec, "Distributing type information") for one such library, covering exactly
the slice of its API the repo calls. Extend the stubs as usage grows — they
deliberately omit everything unused, so a new call site fails type checking
until its signature is added.

No manual install: `convention_cards` declares these packages in its `dev`
dependency group as local path dependencies, so `uv sync` builds them into the
workspace environment that mypy checks against.
