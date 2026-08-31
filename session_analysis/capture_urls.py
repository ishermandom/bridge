# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Where each fetched capture came from.

A capture's place in the tree says which site published it, but not the URL it
was fetched from, and a capture saved by hand never had one. The fetchers know
the URL as they save, so they write it beside the capture and `traveller_store`
reads it back into the stored traveller's `CaptureReference`.

The URL sits in a sidecar named for the capture: `foo.html` is accompanied
by `foo.html.url`, holding the one URL as a line of text. Keeping it beside
the capture rather than in a per-directory index means provenance travels with
the file — moving a capture and its sidecar together carries the URL along,
where an index would have to be rewritten to match — and two fetches saving into
one directory never contend for the same file.

A sidecar is an ordinary file, which is why this module hands out a path and
some bytes rather than writing anything: a fetcher already has a writer, and
giving it a second one to record provenance would be two ways to put a file on
disk where one will do.

A capture with no sidecar is one nothing recorded a URL for: saved by hand, or
filed before this existed. Its reference then carries no URL at all, which is
the honest answer — a URL guessed from the path would look identical to a real
one while being wrong for exactly the captures that were saved by hand.
"""

from pathlib import Path

from session_analysis import issue_reporting
from session_analysis.enums import IssueSeverity

# A sidecar that is there but says nothing. The capture it belongs to is
# still worth storing, so this costs that record its URL rather than the
# whole run — the same discipline the parsers hold to within a capture.
_UNREADABLE_SIDECAR = issue_reporting.Failure(
  'unreadable_sidecar', IssueSeverity.LOW, 'capture'
)

URL_SUFFIX = '.url'


def sidecar_for(capture: Path) -> Path:
  """The sidecar holding `capture`'s URL.

  The suffix is appended rather than substituted, so a capture keeps its whole
  name and two captures differing only by extension get separate sidecars.
  """
  return capture.with_name(capture.name + URL_SUFFIX)


def sidecar_contents(url: str) -> bytes:
  """What a sidecar holds for `url` — the writing half of `read_url`."""
  return f'{url}\n'.encode()


def read_url(capture: Path) -> issue_reporting.Read[str | None]:
  """The URL `capture` was fetched from, or None if nothing recorded one.

  A sidecar that is there but empty comes back as no URL and an issue: only
  `sidecar_contents` should be writing these, so an empty one means something
  else did, and that is worth a person\'s attention even though the capture
  behind it parses perfectly well.
  """
  sidecar = sidecar_for(capture)
  if not sidecar.is_file():
    return issue_reporting.Read(None)

  url = sidecar.read_text().strip()
  if not url:
    return issue_reporting.Read(
      None, (_UNREADABLE_SIDECAR.issue(f'{sidecar.name} holds no URL'),)
    )
  return issue_reporting.Read(url)
