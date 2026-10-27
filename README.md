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

The analyzer answers the classic question "how do I play this suit?" — not from
memory, but by working through every way the defenders' cards can lie. Given the
number of tricks wanted, it finds the line of play most likely to take at least
that many tricks against best defense. It also reports how often that line
succeeds, and why.

It is both a library and a small command-line tool. Name North's and South's
cards and the tricks wanted:

```sh
cargo run --release --manifest-path suit_combinations/Cargo.toml -- AQT-xx@2
```

```text
AQT-xx@2: 76.00%
Low to the T, then low to the Q
Finesse hoping the K or J is onside
```

Major kudos to the excellent pre-existing tools in this space, notably including
[Bridge CCAnalyser](https://bridge.esmarkkappel.dk) and
[SuitPlay](https://jeroenwarmerdam.pythonanywhere.com/suitplay/). Unlike these
existing tools, this repo's analyzer explains the line the way a teacher would,
in a sentence or two of English, alongside the percentage. For now it assumes
unlimited entries and nothing known about the defenders' hands.

Its reported percentages can be checked against SuitPlay, a Windows program.
`suit_combinations/suitplay/run.sh` runs SuitPlay inside a small Linux virtual
machine on a file of holdings, one per line such as `AQT-xx`, and prints
SuitPlay's best-line percentage for each trick target; `compare-suitplay` then
lists every target where the two disagree:

```sh
suit_combinations/suitplay/run.sh holdings.txt > suitplay.tsv
cargo run --release --manifest-path suit_combinations/Cargo.toml -- \
  compare-suitplay suitplay.tsv
```

This needs [Lima](https://lima-vm.io/) (`brew install lima`) and a copy of
`SuitPlay.exe` in `/Users/Shared/data/bridge/suitplay/`. The first run builds
the virtual machine, which takes a few minutes and about 5 GB of disk. SuitPlay
first shows its license agreement; `run.sh holdings.txt --accept-license`
accepts it. SuitPlay takes a few seconds for most holdings, but can take minutes
when many cards are missing; `--minutes-per-holding` sets how long `run.sh`
waits on one holding before giving up on it.

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

### System notes renderer

`system_notes/` — Python

Renders a partnership's system notes into three outputs from one source: a
self-contained HTML page for the screen, a two-column US-letter PDF whose table
of contents and cross-references carry page numbers, and a hard-wrapped
plain-text rendering for pasting into email. The notes are a long, deeply nested
bidding and carding agreement written in Pandoc Markdown. See
`system_notes/spec.md` for the design.

The notes themselves are partnership agreements and live in the private
companion repository; only the renderer and an AI-drafted sample document
(`system_notes/fixture/notes.md`, unreviewed and not a workable system) live
here.

Prerequisites beyond `uv` are listed in `system_notes/Brewfile`; install them
with `brew bundle --file system_notes/Brewfile`. Run that as the account that
renders, since a font cask installs into the running account's
`~/Library/Fonts`. Render, from the repo root, with

    uv run --project . python -m system_notes.render_notes path/to/notes.md

which writes `notes.html`, `notes.pdf`, and `notes.txt` beside the input. A
render fails if the PDF embeds a font the stylesheet never asked for, which
means some text fell back to whatever the machine happened to have.

The Markdown is ordinary Pandoc Markdown plus a few conventions:

- Bids are written plainly — `4S`, `2NT`, `3C` — and the renderer draws the suit
  symbol. Notrump is always `NT`; a bare `N` after a level fails the render.
- `!S !H !D !C` ask for a suit symbol outside a bid, as in `a !H lead`.
- A shorthand compound ending in the major-suit placeholder `M` — `OM`, `W2M`,
  `4cM` — gets that `M` bolded automatically; ordinary words (`IMP`, `BAM`) and
  the minor's lowercase `m` stay plain. Write compounds apart, as `4cM & 5+m`,
  so each one ends its own word.
- A link to a heading id — `[Stayman](#stayman)` — carries that heading's page
  number in print, as "Stayman (p. 4)". Left empty, `[](#stayman)` takes the
  heading's own title for its text. Give headings explicit ids
  (`## Stayman {#stayman}`) so references survive retitling.
- Card-count ranges such as `15–17` and slashed shorthand such as `P/C` never
  break across lines; other hyphenated and slashed words wrap normally.
- The YAML block needs a `title`. Heading levels must not skip (no `###`
  directly under a `#`), and every internal link must point at a heading that
  exists.

After an intentional change to the rendering, run
`uv run --project . python -m system_notes.update_goldens` and review the golden
diff.

### Session analysis (exploratory)

`session_analysis/` — Python

A longer-term, still-speculative idea: turn a night of bridge into something to
learn from, automatically. The envisioned pipeline scans a handwritten
scoresheet, fetches the official hand records for the session, and compares the
contracts and results reached against the double-dummy analysis — surfacing the
deals where the table diverged most from optimal play.

This depends on the double-dummy solver and is the least defined of the
projects; treat it as a direction, not a commitment.

### Squeeze trainer (prototype)

`practice/squeezes/` — Python + TypeScript

A BridgeMaster-style declarer-play trainer for deep-diving one technique at a
time, starting with squeeze play. The robot defenders' hands are deliberately
not fixed: the engine tracks every layout consistent with the play so far, so
only a line that handles all of them succeeds — the correct technique, not a
memorized layout. Currently a prototype under `practice/squeezes/scratch/`; see
`practice/squeezes/spec.md` for the design.

## Licensing

This repository is dual-licensed to reflect the difference between code and
educational content:

- **Code** is licensed under the [MIT License](LICENSE).
- **The publishable flashcard content** in `flashcards/` is licensed under
  [Creative Commons Attribution 4.0 International (CC-BY-4.0)](flashcards/LICENSE)
  — free to use, share, and adapt, including commercially, as long as you give
  credit.

Copyright 2026 Ilya Sherman (ishermandom@).
