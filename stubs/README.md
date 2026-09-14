# Local type stubs

Some dependencies ship no type information, and the repo holds Python to mypy's
strict mode, so each subdirectory here is a minimal stub-only package (typing
spec, "Distributing type information") for one such library, covering exactly
the slice of its API the repo calls. Extend the stubs as usage grows — they
deliberately omit everything unused, so a new call site fails type checking
until its signature is added.

No manual install: `convention_cards` declares these packages in its `dev`
dependency group as editable local path dependencies, so `uv sync` installs each
one as a pointer to its directory here, and an edited stub takes effect on the
next type check.

## Build backend {#build-backend}

Type checkers follow an editable install only when it is a plain path entry, so
the packages build with a backend that writes one: uv's own, `uv_build`.

setuptools, the usual default, was considered and rejected. Its default editable
install is an import hook, which mypy and pyright cannot follow; its plain-path
mode, `editable_mode=compat`, is slated for removal.

The packages require `uv_build` with no upper bound. A release that broke these
stubs would fail loudly, at install or type check, and fixing that then costs
less than raising a cap by hand at every minor uv release.
