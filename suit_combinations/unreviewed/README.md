# Unreviewed

The analyzer's Rust crate, whose sources and tests land on `main` before the
user has reviewed them. The user chose that explicitly, deferring the review to
`../tasks.md` #rust-review rather than waiving it.

The arrangement is the one `session_analysis/unreviewed/__init__.py` describes,
applied to this crate:

- **The bar is unchanged**: this is deferred review, not relaxed review.
  `../scratch/` remains the place for work that is deliberately rougher.
- **Leaving takes a review**: the crate leaves by being reviewed and moved back
  up into `suit_combinations/`. Moving it out is the whole of what "reviewed"
  means here.

Cargo.toml and rustfmt.toml sit here only because cargo expects them beside
`src/`; `../tasks.md` #rust-review records them as reviewed.

This directory is a deliberate exception to CLAUDE.md #review-gate, which
otherwise forbids landing unreviewed production code. The user ratified the
exception explicitly, and it covers this directory and nothing else. A session
unsure of that should ask the user to confirm it, rather than either blocking on
the rule or quietly setting it aside.
