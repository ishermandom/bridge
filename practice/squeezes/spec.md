# Squeeze trainer

A BridgeMaster-style declarer-play trainer for deep-diving one topic at a time,
starting with squeeze play: play constructed positions against robot defenders
whose hands are not fixed, so only the correct _technique_ wins — previewing a
layout and playing double dummy against it is impossible by design.

## The quantum-defenders model {#quantum-defenders}

A problem is not a deal. It is:

- declarer's and dummy's cards (fixed and visible),
- a **family of layouts** — every way the defenders' cards might lie that the
  problem intends to pose, and
- a trick target for the declarer side.

The defenders commit to nothing until play forces them. Every defender card
played filters the family down to the layouts consistent with the play so far
(card ownership and follow-suit voids both filter). Declarer "wins" a problem
only with a single uniform line that reaches the target against **every** layout
the family still allows — exactly the standard a squeeze meets and a
peek-then-finesse line fails.

Rationale: fixing a layout (as published problems do) lets a student replay the
deal double dummy. The family restores the real skill: choosing a line that
handles every lie the position admits, and reading defenders' discards as they
reveal which lie holds.

## Exact game solver, not double-dummy per layout {#exact-solver}

The engine solves the single-dummy game exhaustively: declarer moves per
information set (own cards, dummy, cards seen), the adversary plays any card
consistent with at least one surviving layout, and the win condition quantifies
over all surviving layouts. This avoids the strategy-fusion trap of "min over
layouts of double-dummy values", which can call a position winnable when no
_uniform_ line exists.

Rationale for not using a DDS library here: endings are small enough (3–6 cards
a hand) that exact search in Python is instant, correctness is provable rather
than approximated, and it avoids a native dependency (`endplay` has no Python
3.14 wheels yet, though it does build from source — verified, so full 13-card
deals can adopt it later).

The same solver drives the robots:

- **Error detection**: after each declarer card, if the position flipped from
  winnable to unwinnable, play stops immediately (BridgeMaster-style) and the
  engine reports a witness — a surviving layout (or pair of layouts) the
  remaining play cannot handle. Any theoretically sufficient card is accepted,
  not just one scripted line.
- **Defender play**: while declarer is on a winning path, defenders play the
  legal card consistent with the most surviving layouts (ties: lowest rank) —
  maximally uninformative, so their carding never leaks the layout. Defender
  spot cards carry no signals, deliberately.

## Problem generation {#generation}

Problems are generated from squeeze matrices (Love's classification), not
harvested from published banks: a published problem is a single fixed layout, so
a family would have to be re-derived from it anyway, and book content is
copyrighted. Generation instantiates a matrix — threat suits, squeeze-card suit,
guard and idle cards — with randomized suit roles and spot cards, so repetition
drills the pattern rather than a memorized deal.

Every generated problem is certified, not trusted:

- the solver proves a uniform winning line exists against the full family;
- the family contains layouts with either defender holding the guards, so no
  one-sided line can pass;
- adding a split-guards layout (each defender guarding one threat) must make the
  position unwinnable — proof that the win rides on one defender being squeezed,
  i.e. that the answer genuinely is the squeeze.

## Scope and curriculum {#curriculum}

Stage 1 (this scratch build): the bread-and-butter **automatic simple squeeze**
— notrump, South declaring and on lead, endings of 3–6 cards with the count
already rectified. Planned follow-ups, in order: positional simple squeezes;
rectifying the count; full 13-card deals (pad an ending with idle cards and
early tricks); mixed sets where roughly half the problems are squeezes and half
are look-alikes best played another way (e.g. a finesse as the percentage line),
which replaces the sure-trick standard with a weighted-family percentage
standard.

## Architecture {#architecture}

- **Backend**: Python, FastAPI (chosen as the professional-standard typed Python
  API framework; also informs the pending Review UI stack choice in
  `session_analysis`). Game sessions are held in memory; this is a single-user
  local tool.
- **Frontend**: React + TypeScript via Vite, in `scratch/ui/`, talking JSON to
  the backend through the Vite dev proxy. React is a deliberate learning choice
  for the project owner.
- **Engine layering**: `cards` (vocabulary) → `problems` (position + layout
  family) → `solver` (exact quantum game search) → `engine` (interactive
  session, error reports, defender policy) → `generation` (matrix templates →
  certified problems) → `server` (HTTP surface). The engine defines its own
  minimal card vocabulary rather than importing `session_analysis`'s pydantic
  models; unifying them is a graduation question.

Everything under `scratch/` is prototype-bar code (see CLAUDE.md
#exploratory-mode) pending graduation to reviewed status.
