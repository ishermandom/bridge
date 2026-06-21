<!--
Copyright 2026 Ilya Sherman (ishermandom@)
SPDX-License-Identifier: CC-BY-4.0
-->

# Flashcards layout and syncing spec

This document specifies how the bridge study deck is organized, where its
authoritative data lives, and how cards flow between the live Anki collection,
the published `flashcards/` content, and an off-Anki backup. It is the design
record for both the published content here and the `anki/` tooling that drives
the syncing. For the user-facing summary of each project and the licensing
split, see the repository [README](../README.md); this spec does not repeat it.

## Goals and scope

The design reconciles three standing tensions:

- **Study grouping vs. published taxonomy.** Review wants like kinds of card
  studied together at a controllable cadence; sharing wants a fine-grained
  published hierarchy. Decks serve the first; tags serve the second and drive
  the published hierarchy.
- **Two origins of truth.** Some cards are hand-authored and edited in the Anki
  app; others are produced by scripts (self-contained, or driven by
  spreadsheets). Each origin owns its cards.
- **A publishable subset inside a larger private deck.** Cards derived from
  copyrighted books and lessons, and private partnership agreements, must never
  reach the public repository; only original, shareable cards do.

In scope: the deck/tag model, note-type conventions, card identity, the data
flows that keep everything in sync, and the directory layout. Out of scope: the
content of individual cards, and the internals of the bridge analyzers (e.g.
`suit_combinations/`) that some generators may call.

## Architecture overview

The **live Anki collection is the hub**. Every card is reviewed there, but no
single store is authoritative for all of them — authority is **split by
origin**:

- **Hand-authored cards** are authored and edited in the Anki app. The live
  collection is their source of truth. Their text reaches version control only
  as a downstream export.
- **Generated cards** are produced by scripts in `anki/`. The script (and any
  spreadsheet feeding it) is their source of truth; the copy in Anki is a
  rebuildable projection. Generated cards are **script-owned and never
  hand-edited** — see
  [Guarding against silent data changes](#guarding-against-silent-data-changes).

Three artifacts derive from the hub:

- the **published `flashcards/` content** — the shareable subset, as readable
  text plus a built importable package;
- a **private backup** — a full, automated, version-tracked snapshot of the
  whole collection, in a separate private repository;
- (transiently) **import packages** that carry generated cards into the hub.

## Locations and artifacts

| Location                 | Contents                                                  | Visibility      |
| ------------------------ | --------------------------------------------------------- | --------------- |
| Live Anki collection     | All cards, reviewed daily; the hub                        | Local + AnkiWeb |
| `flashcards/` (this dir) | Published card text + built package; CC-BY                | Public          |
| `anki/`                  | Python tooling: note types, generators, sync scripts; MIT | Public          |
| Backup repository        | Full-collection JSON dump + `.apkg` snapshot              | Private         |
| Local spreadsheets       | Inputs to sheet-driven generators; may hold private data  | Local only      |

The split follows the README's project boundary: `anki/` is code, `flashcards/`
is content. Note types are code (genanki model definitions) and live in `anki/`;
the expanded public card text lives in `flashcards/`. Spreadsheets that drive
generators may contain private partnership data and so stay out of every public
repository — local only, or in the private backup repository.

## Organization: decks and tags

Anki places each card in exactly one deck but allows many tags. We use that
asymmetry directly: **decks are scheduling units, tags carry the taxonomy.**

### Decks (study grouping and cadence)

Switching between unlike kinds of card — a bidding agreement, then a defense
problem — carries a context-switch cost with no offsetting benefit: these are
distinct skills, not confusable ones whose discrimination rewards interleaving.
So decks are organized **one per category**, and a session drills a single kind:

```text
Bridge::Bidding (deep)
Bridge::Shapes (quick)
Bridge::Probabilities (quick)
Bridge::Lead agreements (quick)
Bridge::Suit combinations (deep)
Bridge::Lead problems (deep)
Bridge::Defense problems (deep)
```

This still honors "decks are scheduling units, tags carry taxonomy": category is
the dimension along which review is actually scheduled and grouped, so it
belongs in decks, while the cross-cutting dimensions (privacy, origin, partner,
probability sub-kind) stay in tags. Each category comfortably clears the ~20–30
cards below which a subdeck should instead be a tag, so this is not the
"hundreds of tiny decks" anti-pattern.

**Cadence** — how often a kind is drilled, and how its intervals grow — is an
Anki **deck-options preset**, not a deck level. Two presets to start: `Quick`
for fast retrievals (shapes, probabilities, lead agreements, BWS recall) and
`Deep` for cards needing minutes of analysis (suit combinations, lead and
defense problems). The preset defaults per category and is overridable per deck.

Study decks are decoupled from the published hierarchy: the publish step builds
public decks from `cat::*` tags (below), independent of how the study decks are
sliced, so the study layout is purely a review-ergonomics choice.

**Interleaving** is deliberately given up here; its retention benefit is
strongest for confusable material and thin for unrelated skills. When it is
wanted — a mixed rapid-fire of all `Quick` cards, say — a **filtered deck**
built from a tag search provides it on demand without disturbing the home decks.

### Tag taxonomy

Tags encode the refined hierarchy that decks deliberately omit. Three orthogonal
families:

- **Category** — `cat::…`, the subject taxonomy that the publish step turns into
  a deck hierarchy. For example:

  ```text
  cat::bidding::bws
  cat::bidding::partnership::<partner>
  cat::shape
  cat::probability::hand-pattern
  cat::probability::suit-break
  cat::probability::hcp
  cat::suit-combination
  cat::lead::agreement
  cat::lead::problem
  cat::defense::problem
  ```

- **Origin** — `origin::generated` or `origin::authored`, recording which store
  is authoritative and whether the card is script-owned. If unspecified, assume
  `origin::authored`. A script should tidy up missing origins, with user
  confirmation.

- **Publishability** — every note carries an explicit `publish::*` label;
  publishing is opt-in, and a missing label is never read as a default.
  `publish::yes` clears a card for the public repository.
  `publish::no::<reason>` keeps it out and records why —
  `publish::no::copyright` (derived from a book or lesson),
  `publish::no::partnership` (a personal agreement), `publish::no::personal`
  (anything else private). An unlabeled note is unresolved and blocks publishing
  until labeled (see [Publish marking](#publish-marking)).

### Publish marking

Publishing is **opt-in and fail-closed**: a card reaches the public repository
only if it explicitly carries `publish::yes`, and anything else is withheld. The
principle is that a card whose status is unclear must never leak, and an unclear
status must be made visible rather than silently swallowed.

The publish build enforces this in three layers:

- **Explicit opt-in.** Only `publish::yes` cards are eligible; `publish::no::*`
  cards are excluded.
- **Unlabeled is a hard error.** A card in scope with no `publish::*` label
  **fails the build**, which lists the offending cards and publishes nothing
  until each is labeled. A missing label is a red flag, surfaced — never a
  guess.
- **Never-public categories.** Categories known to be unpublishable (e.g.
  `cat::bidding::partnership::*`, anything copyright-derived) are on a
  never-public list. The build refuses to publish a card in those categories
  even if it is mistagged `publish::yes`, unless that card carries a deliberate,
  auditable override. This catches a fat-fingered opt-in on private material.

Generators stamp the label at generation time, so no generated card is ever
unlabeled; hand-authored cards are labeled by the author, and the
unlabeled-is-error check guarantees none is forgotten. A standalone lint that
reports unlabeled or never-public-but-opted-in cards lets the collection be
audited without running a full build.

## Card categories and note types

### Note-type conventions

Each category maps to an Anki note type (genanki model) declared in `anki/` and
used by **both** the live collection and every build, so imports match cleanly.
Two invariants make that work:

- **Model IDs are frozen constants.** genanki identifies a note type by a
  numeric model ID; the same ID must be used everywhere and never changed, or
  imports create a divergent copy.
- **Rendering is shared.** A single styling include defines suit-symbol
  rendering (♠ ♥ ♦ ♣ with red/black coloring), auction tables, and hand
  diagrams, so every category renders bridge content consistently.
- **Built-ins where nothing custom is needed.** A category that needs no special
  rendering reuses Anki's built-in `Basic` type — probabilities, for instance,
  are plain question/answer text. genanki ships a matching `Basic` model so the
  build stays consistent.

### Note-type versioning and evolution

A note type has two parts that evolve very differently, and each is handled
where it is safest. The **declared definition** — fields, templates, CSS, and
the **permanent model ID** (never changed; a new ID would orphan every existing
note of that type) — lives in the repository as the versioned, machine-readable
record. It is what the build reads to construct genanki models, the audit trail
of how a type changed, and the baseline the schema validation checks against.

**Templates and CSS** carry no data-migration risk and change often. The repo is
their authoring surface; edits reach the live collection through AnkiConnect
(`updateModelTemplates` / `updateModelStyling`). Importing a deck does _not_
update an existing note type's templates, so this push — not a card re-import —
is how a rendering change lands.

**Field-schema changes** — renaming, removing, or reordering fields — are rare,
data-bearing, and best judged interactively, with Anki's UI showing the old→new
field mapping, confirming destructive actions, and flagging the full sync the
change forces. So the schema edit is made by hand in Anki's Fields / Change
Notetype dialog rather than automated: for this dimension Anki is the authoring
surface and the repo declaration is reconciled to match. Automating it would
mean maintaining rarely-run migration code on a high-stakes path; the UI's
decision support is worth more than the automation. The edit is instead
bracketed by automated safety — a snapshot before and a validation after — so
the fragile live store is never mutated without a recoverable checkpoint and an
after-the-fact check; see
[Schema changes: snapshot and validate](#schema-changes-snapshot-and-validate).

Adding a field is the one safe schema change: it is backward-compatible (empty
on existing notes until populated) and needs no migration. A breaking change
also touches every generator that writes the type, since they share the field
contract, so those generator updates land in the same commit as the declaration.

Disaster recovery restores the collection from a backup snapshot, not by
replaying a migration history, so the manual, un-replayable nature of a schema
edit costs nothing the system depends on.

### Categories

The origin and publish label below are what generators stamp, and the expected
value for hand-authored cards; both are per-card tags and can be overridden per
card. The publish label is never inferred — an unlabeled card is an error (see
[Publish marking](#publish-marking)).

| Category               | Note type           | Default origin     | Publish label              | guid natural key        |
| ---------------------- | ------------------- | ------------------ | -------------------------- | ----------------------- |
| BWS bidding agreement  | `Bidding agreement` | Authored           | `publish::yes`             | Auction string          |
| Partnership agreement  | `Bidding agreement` | Authored           | `publish::no::partnership` | Partner + auction       |
| Shapes                 | `Shape`             | Generated (script) | `publish::yes`             | The known suit lengths  |
| Probabilities          | `Basic` (built-in)  | Generated (script) | `publish::yes`             | The structured question |
| Suit combination       | `Suit combination`  | Generated (sheet)  | `publish::yes`             | Both holdings           |
| Opening lead agreement | `Opening lead`      | Generated (script) | `publish::yes`             | Holding + context       |
| Opening lead problem   | `Lead problem`      | Generated (sheet)  | `publish::no::copyright`   | Full deal + auction     |
| Defense problem        | `Defense problem`   | Generated (sheet)  | `publish::no::copyright`   | Full deal + auction     |

The category set is open; new categories add a row, a note type, and (if
generated) a generator. The `Bidding agreement` note type is shared by the BWS
and partnership categories, distinguished by tag rather than by a separate type.
Shapes and `cat::probability::hand-pattern` are kept as separate categories —
the shape-completion drill versus the odds of a shape. Whether they should merge
is left open until those cards are built.

## Card identity and idempotency

Generated cards must re-import without duplicating and without discarding review
history. Identity is a **deterministic GUID derived from the card's natural
key**, via `genanki.guid_for(...)` over the key in the table above. On import,
Anki matches by GUID: a changed field updates the existing note in place and
preserves its scheduling; an unchanged card is a no-op. Because identity is the
hidden GUID rather than a visible field, any field — including the card's front
— can change without breaking the match. This is strictly more robust than
Anki's default first-field matching, where editing the primary field orphans the
old note and creates a duplicate.

The natural-key formula for each category is therefore a **frozen contract**:
changing how a key is computed re-mints GUIDs and produces duplicates on the
next import. Keys are recorded above and must be treated as stable.

Hand-authored cards keep the GUID Anki assigns at creation; the export flow
reads that GUID rather than minting one.

## Data flows

Four flows keep the stores in sync. All run with the Anki desktop app open,
using AnkiConnect; none requires a headless toolchain.

### Flow 1 — generate (scripts → hub)

A generator in `anki/` produces its cards, assigns each a deterministic GUID,
and builds a genanki `.apkg`. The package is imported into the live collection —
automated via AnkiConnect's `importPackage`, gated by the diff in
[Guarding against silent data changes](#guarding-against-silent-data-changes).
The same run emits the public subset of those cards as expanded text under
`flashcards/cards/` (see Flow 3).

The manual-validation procedure for this flow — the reviewable dry-run, the
confirmation gate, and the post-import spot-check — is defined under
[Guarding against silent data changes](#guarding-against-silent-data-changes).

### Flow 2 — export (hub → published text)

AnkiConnect queries the collection for hand-authored, public cards (`findNotes`
by tag, then `notesInfo`), and serializes them to per-category text under
`flashcards/cards/`. This is the only path by which hand-authored content
reaches version control; the live collection remains its source of truth, and
the exported text is regenerated, not hand-edited.

### Flow 3 — publish (text → importable package)

genanki builds the public `.apkg` from everything under `flashcards/cards/`
(generated public subset from Flow 1, plus exported hand-authored cards from
Flow 2) together with the note types in `anki/`. The publish step applies the
[publish marking](#publish-marking) rules — only `publish::yes` cards ship, an
unlabeled card fails the build, and never-public categories are blocked. The
built package is a release artifact, not committed source; the committed source
is the readable text under `flashcards/cards/`.

### Flow 4 — backup (hub → private repository)

One scheduled, fully automated script writes two artifacts to a separate private
repository:

- a **deterministic JSON dump** of all notes and note types, produced directly
  through AnkiConnect (`findNotes deck:*` → `notesInfo`, stable-sorted) — the
  diffable, version-tracked record of the whole collection, private cards
  included;
- a **full `.apkg`** of all decks with scheduling (`exportPackage`,
  `includeSched: true`) — the full-fidelity restore artifact.

We serialize our own JSON rather than driving the CrowdAnki add-on: CrowdAnki's
export is a manual UI action with no AnkiConnect hook, and its only advantage —
its specific schema — matters mainly for re-import, which a backup does not
need. Owning the schema keeps diffs clean and the job scriptable, which is the
whole point: a backup that needs a manual step will not happen. The collection
is text-only, so neither artifact carries media and the `.apkg` stays small.

## Guarding against silent data changes

The guiding principle: **no change reaches a store of record without being
reviewed first.** What differs is the _mechanism_, by store:

- **Version-controlled targets** (the repo text, the backup repository) are
  reviewed in `git diff` at commit time, before the change is recorded, and git
  preserves recovery.
- **The live Anki collection** is the one store that is both irreplaceable — it
  holds review and scheduling history that cannot be regenerated — and not
  version-controlled, so it cannot lean on after-the-fact git recovery. Writes
  into it carry the highest stakes and get an explicit guard, one for each of
  the two ways a write reaches it.

### Generated-card imports: the dry-run

Anki's own import reports only aggregate counts ("N updated"), so a regeneration
could silently overwrite a field. Before Flow 1 writes anything, the tooling
produces a reviewable, field-level diff of what the import would do, and applies
nothing without explicit confirmation:

1. **Scope.** Consider only the cards this generator owns (by category and
   `origin::generated`), so the diff never false-flags unrelated cards.
2. **Diff.** For the incoming GUIDs, read the live collection (AnkiConnect) and
   classify each card:
   - **Added** — GUID not in the collection; show the card's key fields.
   - **Changed** — GUID present with differing content; show, per changed field,
     `before → after` under the card's natural key as a heading, so it is clear
     which card changed and how.
   - **Removed** — a GUID the generator no longer produces but that still exists
     under its ownership; show the card key.
   - **Unchanged** — counted only.
3. **Review.** The diff is printed for a small batch and written to a
   timestamped file for a large one (with a printed summary and path), so the
   changes are legible rather than a bare count.
4. **Confirm.** No write happens without explicit confirmation.
5. **Apply.** On confirmation, add and update via `importPackage`. **Removals
   are not applied automatically** — deleting a card destroys its review
   history, so removed cards are reported and left in place unless an explicit
   prune is requested.
6. **Spot-check.** After import, re-read the affected GUIDs and assert the live
   fields match what was pushed, closing the loop that the import did what the
   diff promised.

### Schema changes: snapshot and validate

A note-type field change reaches the collection by hand, through Anki's UI (for
the reasons in [Note-type versioning](#note-type-versioning-and-evolution)), so
its guard is checkpoint-and-verify rather than a pre-flight diff — a stronger
net for a manual, irreversible operation:

1. **Snapshot.** Take a full collection backup immediately before — a guaranteed
   restore point that makes a mis-step reversible.
2. **Change.** Make the field change in Anki's Fields / Change Notetype dialog,
   then update the repo's note-type declaration to match.
3. **Validate.** An automated check confirms the change did exactly what was
   intended: the live note type matches the updated repo declaration (fields,
   order, templates, CSS, model ID), the note count is unchanged, and a
   comparison against the snapshot confirms the data moved as expected (e.g. a
   renamed field's values carried over). It fails loudly on any mismatch — the
   snapshot covers rollback, and the live-vs-declaration comparison also catches
   a forgotten reconciliation.

### Working with generated cards

Generated cards are script-owned, so hand-editing one in Anki does not stick —
the next regeneration reverts it, and the dry-run shows that revert. A change
worth keeping goes back into the generator input, or the card is reclassed as
hand-authored (`origin::authored`). This is a workflow convention; the dry-run
above is what actually prevents silent loss.

## Tooling stack

- **genanki** — builds every `.apkg` (Flow 1 import packages and the Flow 3
  public package) and mints deterministic GUIDs. Requires Anki **2.1.54+** on
  the import side.
- **AnkiConnect** — the read/write bridge to the live collection: pushing
  generated packages (Flow 1), exporting hand-authored cards (Flow 2), the
  dry-run diff, and the backup dump and package export (Flow 4). Requires the
  desktop app to be running, which the workflow assumes.

CrowdAnki and headless tools (apy, the `anki` library directly) were considered
and are not used: CrowdAnki because its export is not scriptable through
AnkiConnect, and headless tooling because a GUI-running workflow is acceptable
and AnkiConnect offers the simpler, more stable API.

## Directory layout

`flashcards/` (public content, CC-BY):

```text
flashcards/
  LICENSE
  spec.md                       # this document
  cards/                        # committed expanded public card text, per category
    suit_combinations.csv
    shapes.csv
    probabilities.csv
    opening_lead_agreements.csv
    bidding_bws.csv
    ...
```

`anki/` (public tooling, MIT) — illustrative; modules are named for what they
do:

```text
anki/
  note_types/                   # genanki models: fields, templates, frozen model IDs
    styling.py                  # shared suit-symbol / auction / diagram rendering
    bidding_agreement.py
    suit_combination.py
    shape.py
    opening_lead.py
    defense_problem.py
  generators/                   # per-category card generators (Flow 1)
    shapes.py
    probabilities.py
    suit_combinations.py
    opening_lead_agreements.py
    bidding_bws.py
  ankiconnect.py                # AnkiConnect client
  identity.py                   # deterministic guid_for natural keys
  diff.py                       # dry-run diff vs the live collection
  publish.py                    # Flow 3 build of the public package
  export.py                     # Flow 2 export of hand-authored cards
  backup.py                     # Flow 4 JSON dump + .apkg export
  tags.py                       # tag taxonomy constants
  decks.py                      # deck and published-hierarchy constants
```

The private backup repository is a separate repository, not a directory here.
The built public `.apkg` is a release artifact and is not committed.

The `anki/` module tree above is indicative; its full form and the build-tool
mechanics are deferred to `anki/spec.md` (see
[Deferred items](#deferred-items)).

## Edge cases and considerations

- **Reclassifying a card.** Generated → authored: retag `origin::authored` and
  stop regenerating it (the generator drops its key). Authored → generated: add
  it to the generator's inputs and let the deterministic GUID take over; the
  previously authored note keeps its Anki GUID, so confirm the keys align or
  expect a one-time duplicate to resolve by hand.
- **Changing a natural-key formula.** Treated as a breaking change: it re-mints
  GUIDs and duplicates cards on import. Migrate deliberately, not incidentally.
- **BWS copyright.** Bridge World Standard is a published document. The bidding
  _agreements_ are conventions, not protectable expression, but verbatim wording
  from the booklet may be. Author BWS cards in original wording, and keep the
  publish determination explicit rather than assuming the category is uniformly
  safe.
- **Partnership privacy.** Partnership agreements are labeled
  `publish::no::partnership` and are additionally on the never-public list, so
  they are withheld by both the opt-in filter and the category guard.
- **`exportPackage` fidelity.** Confirm at build time that AnkiConnect's
  `exportPackage` with `includeSched: true` covers all decks and captures
  scheduling; AnkiConnect exposes `.apkg`, not `.colpkg`, but for a text-only
  collection an all-decks `.apkg` with scheduling is equivalent for restore.
- **CSV-with-GUID fallback.** A trivially simple generator may import via a CSV
  carrying a `guid` column (Anki 2.1.54+) instead of building an `.apkg`. The
  identity guarantees are the same; verify the column mechanism if used.
- **Concurrency.** AnkiConnect operates on the running app, so the GUI-open
  workflow is safe; do not also open the collection with a headless tool, which
  would contend for the database lock.

## Testing strategy

- **Generators** — given fixed inputs, assert the produced card fields, and
  assert GUID determinism: identical input yields an identical GUID, distinct
  inputs distinct GUIDs. Use representative bridge holdings chosen to exercise
  edge cases; bridge hands carry no privacy concern, so they need not be
  schematic. Reserve placeholders for anything personal — e.g. a `<partner>`
  stand-in in partnership-card tests.
- **Identity** — pin `guid_for` against a golden set so a key-formula change is
  caught as a deliberate edit, not a silent regression.
- **Diff** — against a mocked AnkiConnect, assert correct `added` / `changed` /
  `removed` classification, including field-level change detection.
- **Publish** — assert that only `publish::yes` cards ship, that
  `publish::no::*` cards and never-public categories are excluded, that an
  unlabeled card fails the build, and that the output is a structurally valid
  importable package.
- **Round-trip** — exporting (Flow 2) then publishing (Flow 3) reproduces the
  expected hand-authored notes.
- **AnkiConnect client** — unit-test against mocked HTTP; reserve any
  live-collection test as an explicit, optional integration check.

## Design decisions

The choices above, with the rationale that would otherwise have to be
reconstructed:

- **Authority split by origin**, not a single source of truth, because the
  workflow genuinely has two: the Anki UI for hand-authored cards and
  scripts/spreadsheets for generated ones. Forcing either to own everything
  would fight the way the cards are actually made.
- **Decks by category, cadence by preset.** Switching between unlike skills
  costs attention without the discrimination benefit that makes interleaving
  worthwhile, so each category is its own deck and review is blocked by kind.
  Cadence rides on deck-options presets rather than a deck level, and the
  cross-cutting dimensions stay in tags — the precise reading of "few decks,
  many tags" is that decks carry the dimension you schedule by, which here is
  category. The interleaving given up is recoverable on demand via filtered
  decks.
- **Opt-in, fail-closed publishing.** A card ships only with an explicit
  `publish::yes`; `publish::no::*` records why a card is withheld; an unlabeled
  card is a build error, never a silent default; and never-public categories are
  blocked even against a mistaken opt-in. Leaking copyrighted or partnership
  material is the expensive error, so a missing label is treated as a red flag,
  not a guess.
- **Readable text as the committed artifact**, with the `.apkg` as a build
  output, so the public repository is inspectable and adaptable rather than an
  opaque binary.
- **Deterministic GUIDs over first-field matching**, so any field can change
  without orphaning the card, and re-imports preserve review history.
- **genanki + AnkiConnect**, dropping CrowdAnki and headless tooling, because a
  GUI-running workflow is acceptable and this pairing covers all four flows with
  the simplest stable APIs.
- **Self-serialized backup JSON**, because the backup must be fully automated to
  actually run, and CrowdAnki's only advantage is a re-import schema a backup
  does not need.

## Deferred items

These are `anki/` tooling mechanics, recorded here so they are not lost and
moved to `anki/spec.md` when that project begins:

- **Card-text standardization.** A helper to normalize card text — suit-symbol
  notation, auction formatting, whitespace — especially for hand-authored cards,
  which lack a generator to enforce consistency.
- **Schema-change safety tooling.** The snapshot and the validation check behind
  [note-type versioning](#note-type-versioning-and-evolution) — comparing the
  live note type against the repo declaration, and the data against the
  pre-change snapshot.
- **Full `anki/` module layout.** The indicative tree under
  [Directory layout](#directory-layout) in its complete form.
