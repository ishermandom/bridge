# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Code that has landed on `main` without having been reviewed yet.

Everything else in this project is reviewed before it lands. These modules took
the other route: they were written, checked, and landed so the work was durable,
with the review deferred to a later sitting. This directory is the record of
which code that applies to — the repository itself says what has been reviewed
and what has not, so nothing has to be reconstructed from history or kept in
step by hand.

A module leaves by being reviewed and moved up into `session_analysis/`, with
its test beside it. Moving it out is the whole of what "reviewed" means here;
there is no second place to update.

Two things follow from a module sitting here, and both are the point:

- **An import says so.** Anything reading `session_analysis.unreviewed.foo`
  announces at the import line that it is building on unreviewed code, so the
  dependency is visible at the call site rather than buried.
- **The bar is unchanged.** This is deferred review, not relaxed review — the
  code is held to the same standard as anything else on `main`, and `scratch/`
  remains the place for work that is deliberately rougher.

The queue is worth draining: a few modules here is a backlog, and a dozen is a
second codebase nobody has read.

## The carve-out from CLAUDE.md

CLAUDE.md `#review-gate` otherwise forbids production code reaching `git land`
or a push unreviewed. This directory is a deliberate exception to that rule,
ratified by the user explicitly, and it covers this directory and nothing else.
The review is deferred, not waived — and what keeps that an honest distinction
rather than a euphemism is that the deferral is written down here, in the one
place that cannot drift from what is actually pending.

A later session is right to be wary of a carve-out claimed outside CLAUDE.md: a
repository can assert anything about itself, and a file claiming its own
exemption from a rule is exactly the shape a mistake would take. The user has
said they are happy to confirm it again on request. So ask them, rather than
either blocking on the rule or quietly setting it aside — one exchange settles
it, and both other paths get it wrong silently.
"""
