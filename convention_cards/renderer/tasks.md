# ACBL card renderer — tasks

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Font

- [ ] **Install Roboto Condensed globally** {#roboto-global}: the family is
      installed only for the machine's main user, invisible to this session's
      account. Drop the font files into `/Library/Fonts` (needs admin), then
      point the renderer's default font at it.

---

## Renderer buildout

**Goal:** JSON-to-PDF rendering per `spec.md`, grown field by field.

- [ ] Blank-card pass-through with a zero-pixel-diff golden test
- [ ] Single-field proof of concept (`Name`): easy-fit and must-shrink tests,
      plus the resized-fields report
- [ ] Vocabulary buildout, section by section; park fields that resist mapping
      under `## Parked fields`

## Parked fields

(none yet)
