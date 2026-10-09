# Flashcard system tasks

Implementation queue for the design in [spec.md](spec.md). Most code lands in
`anki/`; published content lands in `flashcards/`.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Suit-combination generator {#suit-combination-generator}

**Goal:** get the first generated cards, suit combinations, into the collection
by hand, ahead of the backup and the automated import. Design in
[`anki/spec.md`](../anki/spec.md).

- [ ] `Suit combination` note type with a frozen model ID: the card in
      `anki/spec.md` #suit-combination-card, with the best line and remarks
      rendered per #text-formatting there.
- [ ] Generator: build the `.apkg` with deterministic GUIDs, the deck, and the
      tags `cat::suit-combination`, `origin::generated`, `publish::yes`. Pull
      forward only what it needs from #identity, `tags.py`, and `decks.py`.
- [ ] First import by hand: back up the collection in Anki (File > Create
      Backup), import the package (File > Import), spot-check a few cards, and
      set the deck's options preset to `Deep`.
  - Rationale: the user chose to put this generator ahead of the backup and the
    automated import. The collection holds no card-combination cards yet, so the
    first import only adds cards.
  - Note: until #dry-run exists, review the export's `git diff` before each
    re-import — the committed export shows exactly which rows changed.

---

## Backup — Flow 4

**Goal:** stand up the automated, version-tracked full-collection backup — the
safety net that makes every later flow's writes to the collection recoverable.

- [ ] `ankiconnect.py` — AnkiConnect client; start with the actions backup needs
      (collection read, `exportPackage`) and extend it in later phases.
      #ankiconnect
- [ ] Create the private backup repository.
- [ ] `backup.py` — deterministic JSON dump plus a full `.apkg`
      (`exportPackage`, `includeSched: true`).
- [ ] Schedule the backup job.

---

## Card foundations

**Goal:** the shared primitives the note types and generators depend on.

- [ ] `tags.py` — tag taxonomy constants: `cat::*`, `origin::*`, `publish::*`.
- [ ] `decks.py` — per-category deck constants and the `Quick` / `Deep` cadence
      option presets.
- [ ] `identity.py` — `guid_for` over each category's natural key. #identity

---

## Note types

**Goal:** declare the note types and shared rendering once, used by both the
live collection and every build.

- [ ] `styling.py` — shared suit-symbol, auction-table, and hand-diagram
      rendering.
- [ ] Per-category note types with frozen model IDs: `bidding_agreement`,
      `shape`, `opening_lead`, `defense_problem`.
- [ ] Reuse Anki's built-in `Basic` (via genanki's Basic model) for
      probabilities.

---

## Generate and import — Flow 1

**Goal:** generate cards and land them in the collection with no silent
overwrites.

- [ ] `diff.py` — dry-run diff against the live collection (added / changed with
      field-level `before → after` / removed / unchanged), built on
      #ankiconnect. #dry-run
- [ ] Import path: build a genanki `.apkg`, gate on #dry-run, `importPackage` on
      confirmation, never auto-delete removals, then post-import spot-check.
- [ ] Generators, one per remaining generated category (`shapes`,
      `probabilities`, `opening_lead_agreements`, `bidding_bws`, lead and
      defense problems). Each stamps `origin` and a `publish::*` label and emits
      its public subset as text to `flashcards/cards/`; built on #identity and
      the note types. Problem generators need full-deal data in their
      spreadsheet (guid key `Full deal + auction`).

---

## Export and publish — Flows 2–3

**Goal:** get the publishable subset out as readable text and an importable
package.

- [ ] `export.py` (Flow 2) — `findNotes` for authored + `publish::yes` cards,
      serialize to `flashcards/cards/`.
- [ ] `publish.py` (Flow 3) — build the public `.apkg` from `flashcards/cards/`
      plus the note types.
- [ ] Publish-marking enforcement: only `publish::yes` ships; an unlabeled card
      is a hard build error; never-public categories are blocked; plus a
      standalone lint to audit without a full build.
- [ ] Emit the suit-combination generator's card text to `flashcards/cards/`,
      which #suit-combination-generator defers; until then the committed input
      file is the public record.

---

## Schema-change safety

**Goal:** evolve note types without losing data.

- [ ] Snapshot-before + validate-after tooling: structure matches the repo
      declaration; note count unchanged; data matches the pre-change snapshot.
- [ ] Template/CSS push via `updateModelTemplates` / `updateModelStyling`.

---

## Backlog

Unsequenced items and open questions from the spec.

- [ ] Restructure the existing collection (currently roughly one deck plus a few
      side-decks) into deck-per-category with cadence presets.
- [ ] Verify `exportPackage` covers all decks and captures scheduling (`.apkg`
      vs `.colpkg`) — confirm while building the backup.
- [ ] Confirm AnkiConnect's `modelField*` data-preservation behavior — confirm
      when first making a schema change.
- [ ] Decide whether `Shapes` and `cat::probability::hand-pattern` should merge
      — revisit when building those cards.
- [ ] Move the spec's Deferred items into `anki/spec.md` (card-text
      standardization, schema-change safety tooling mechanics, full module
      layout).
- [ ] Consider further suit-combination columns: conditions such as entries or
      bidding information, a most-tricks-on-average goal, and technique tags.
  - Note: each can arrive later without re-keying existing cards, because blank
    optional columns stay out of the key.
- [ ] Settle which license covers `spec.md` and `tasks.md` in this directory.
      The README and `flashcards/LICENSE` both scope CC-BY-4.0 to the flashcard
      _content_ here, which doesn't obviously reach development docs that merely
      live alongside it.
  - Open question: widen CC-BY-4.0 to the whole directory, or say the docs stay
    MIT? Their per-file headers claimed CC-BY-4.0 before the headers came out.
