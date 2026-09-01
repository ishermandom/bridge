# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Naming a digitized session from what its sheet says.

The session key identifies one session — `pabc-morn-2026-06-29` — and is what a
record is filed under. It is derived from the footer alone: the event text as
written, normalized, joined to the parsed date. Nothing else is consulted,
because nothing else is available at ingest time.

Deriving it from the sheet alone is a deliberate narrowing. The key was once
meant to be re-derived identically from a traveller capture too, so that
matching a capture to its session was key equality — but the sources spell one
session's event four different ways (`John & Will's Monday Bridge`, `Palo Alto
Duplicate`), and no normalization rule takes all of them to one slug. So the key
names a session and `session_matching` decides what belongs to it; travellers.md
`#matching` covers the split.

The normalization is deliberately literal: whatever was written, lowercased and
hyphenated. Two spellings of one game (`PABC morn.` one week, `PABC Morning` the
next) therefore produce two slugs, which is a known cost — tasks.md
`#canonical-slug` queues the alias table that fixes it.
"""

import datetime
import re

# A run of anything that cannot appear in a slug, collapsed to one hyphen. The
# surviving alphabet is `[a-z0-9-]`, so a derived key is always safe as a
# filename without further escaping.
_NON_SLUG_RUN = re.compile(r'[^a-z0-9]+')

# The stem a record takes when its footer yielded no key at all. The content
# hash keeps it unique and ties the file to the scan it came from, and the
# prefix says plainly that this one still needs a name.
_UNNAMED_PREFIX = 'unnamed'

# How much of a content hash stands in for the whole in a filename. Long enough
# that two scans colliding on it is not a practical concern at a few hundred
# sessions, short enough to leave the rest of the name readable.
_SHORT_HASH_LENGTH = 12


def short_hash(content_hash: str) -> str:
  """The abbreviated content hash that names files derived from one scan.

  Both the archived scan and an unnamed record lead with it, so a scan and what
  came of it can be found from each other without opening either.
  """
  return content_hash[:_SHORT_HASH_LENGTH]


def derive_session_key(event: str, date: datetime.date | None) -> str | None:
  """The key a footer's event text and date name, or None if they cannot.

  Both halves are required: a key with no date does not identify a session, and
  one with no event cannot tell a two-game day apart. `None` is an ordinary
  outcome rather than an error — an unreadable footer still produces a stored,
  reviewable record (models.md `#nothing-is-garbage`), just not a named one.
  """
  slug = _NON_SLUG_RUN.sub('-', event.casefold()).strip('-')
  if not slug or not date:
    return None
  return f'{slug}-{date:%Y-%m-%d}'


def record_stem(session_key: str | None, content_hash: str) -> str:
  """What a pending record and its archived scan are called on disk.

  The key when there is one, so a pending record is recognizable at a glance;
  otherwise a name built from the content hash, which is the one handle an
  unnamed session always has. Review renames the record either way, once a
  person has confirmed what the footer said.
  """
  return session_key or f'{_UNNAMED_PREFIX}-{short_hash(content_hash)}'
