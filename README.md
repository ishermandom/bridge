# Bridge

A collection of tools and study materials for the card game of
[contract bridge](https://en.wikipedia.org/wiki/Contract_bridge). The projects
here span analysis (working out the best line in a deal), study (managing and
sharing flashcards), and the day-to-day logistics of playing at a local club.

## Projects

Each project lives in its own top-level directory. Performance-sensitive
analysis is written in Rust; most tooling and automation in Python, with
browser-side userscripts in JavaScript.

Note that most of the projects are currently only dreamed, and not yet started.
This is a personal, hobby repository. Projects arrive over time and graduate
from "planned" to "working" as they're built.

### Suit-combination analyzer

`suit_combinations/` — Rust

Given a single suit held between two hands, work out the line of play that
maximizes the expected number of tricks (or the chance of a target number of
tricks) against best defense. This is the classic "how do I play this suit"
question, answered exhaustively rather than from memory.

The aim is both a library and a small command-line tool: describe the cards held
in each hand, and get back the optimal line together with its trick expectation.
Unlike existing tools such as https://bridge.esmarkkappel.dk/main/main.html, the
goal is to provide a brief intuitive explanation alongside the best line of
play.

### Double-dummy solver

`double_dummy/` — Rust

A double-dummy solver evaluates a complete deal — all four hands visible — to
determine, with perfect play by everyone, exactly how many tricks each side can
take in each strain. It's the ground truth against which real-world bidding and
play are measured.

The goal is a correct, fast solver usable as a library by the other projects
here (notably session analysis below), plus a command-line entry point for
one-off deals.

Related work: https://mirgo2.co.uk/bridgesolver/ ->
https://dds.bridgewebs.com/bridgesolver/upload.htm

### Anki tooling

`anki/` — Python

Utilities for managing a personal bridge study deck in
[Anki](https://apps.ankiweb.net/), treating the flashcards as version-controlled
source rather than as opaque state inside the Anki app. The intent is to author,
organize, and review cards from plain-text sources, and to keep the deck
reproducible.

TBD: Some flashcards cannot be published (see below). How exactly is the source
of truth synced?

### Publishable flashcards

`flashcards/` — content

The subset of the study deck that is safe to share publicly: original cards
authored from scratch, free of any third-party copyrighted material. The full
personal deck includes cards built around others' books and lessons for private
self-study; those are deliberately kept out of this repository, and only the
clean, original subset is published here.

See [licensing](#licensing) below — this content carries a different license
from the code.

### Club website tooling

`club_sites/` — JavaScript (userscripts)

Per-club userscripts that add personal conveniences to a club's website — the
kind of repetitive logistics that are tedious by hand. Each club lives in its
own subdirectory.

- `club_sites/palo_alto/` — a Tampermonkey userscript for the Palo Alto Bridge
  Center reservations page: a remembered identity (prefilled name, email, and
  playing direction), the game list expanded by default, and a guard against
  accidentally booking a limited game such as EZ Bridge.

### Convention card printing

`convention_cards/` — Python

Merges a convention card PDF (as downloaded from
[BridgeWinners](https://bridgewinners.com/)) with a fold-over strip of personal
bidding reminders, producing a single print-ready PDF: the card on the bottom
8.5", the reminders on the top 2.5" so they fold behind the card and tuck away
in a card holder.

The card content and reminders themselves are personal/partnership data and kept
in a private companion repository — only the generation tool lives here.

A Streamlit webapp wrapping the tool is deployed on Render at
https://ruffdraft.onrender.com. Render deploys from
`convention_cards/requirements.txt`, a `uv export` snapshot rather than the
workspace's own `uv.lock` (Streamlit Community Cloud was the original hosting
choice, but its GitHub OAuth integration requires write access to every public
repo on the account; Render's GitHub App can be scoped to this repo alone).
Regenerate that file after any dependency change:

    uv export --format requirements.txt --package convention-cards --no-dev \
      --no-hashes -o convention_cards/requirements.txt

### Session analysis (exploratory)

`session_analysis/` — Python

A longer-term, still-speculative idea: turn a night of bridge into something to
learn from, automatically. The envisioned pipeline scans a handwritten
scoresheet, fetches the official hand records for the session, and compares the
contracts and results reached against the double-dummy analysis — surfacing the
deals where the table diverged most from optimal play.

This depends on the double-dummy solver and is the least defined of the
projects; treat it as a direction, not a commitment.

## Licensing

This repository is dual-licensed to reflect the difference between code and
educational content:

- **Code** is licensed under the [MIT License](LICENSE).
- **The publishable flashcard content** in `flashcards/` is licensed under
  [Creative Commons Attribution 4.0 International (CC-BY-4.0)](flashcards/LICENSE)
  — free to use, share, and adapt, including commercially, as long as you give
  credit.

Copyright 2026 Ilya Sherman (ishermandom@).
