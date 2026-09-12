# Local type stubs

`pypdfium2` ships no type information, and the repo's mypy runs `--strict`, so
this directory holds a minimal stub-only package (typing spec, "Distributing
type information") covering exactly the slice of its API the repo calls. Extend
the stubs as usage grows — they deliberately omit everything unused, so a new
call site fails type checking until its signature is added here.

No manual install: `convention_cards` declares this package in its `dev`
dependency group as a local path dependency, so `uv sync` builds it into the
workspace environment that mypy checks against.
