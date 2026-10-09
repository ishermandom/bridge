# Anki tooling spec

This document specifies how the `anki/` tooling's generators turn their inputs
into cards. The system those cards live in — decks, tags, card identity, and the
flows between the live Anki collection and the repository — is specified in
[`flashcards/spec.md`](../flashcards/spec.md), which this spec builds on rather
than restates.

## Suit-combination generator

The generator turns the user's list of suit combinations, kept in a Google
Sheets spreadsheet, into one Anki card per row. Each card asks how to play a
holding for a target number of tricks.

### Input file {#suit-combination-input}

The user downloads the sheet as CSV (File > Download > CSV) and commits it as
`flashcards/input/suit_combinations.csv`. A manual download needs no credentials
or setup; reading the sheet directly can be added later without changing
anything downstream.

Each row is one entry, under these headers:

| Header        | Holds                                              |
| ------------- | -------------------------------------------------- |
| North         | North's holding; see [notation](#holding-notation) |
| South         | South's holding, in the same notation              |
| Tricks target | The target, as the source states it                |
| Success %     | The chance that the best line reaches the target   |
| Best line     | A succinct description of the best line            |
| Remarks       | Extended reasoning                                 |
| Source        | A citation for why the combination is on the list  |

The generator skips two things:

- **Comment rows**: a row whose first cell starts with `#`, such as a label for
  the rows below it. A comment row with data in any other cell is an error.
- **Empty unnamed columns**: Google Sheets pads rows with them. An unnamed
  column holding data is an error.

In every other row, Remarks and Source may be blank, and a blank North or South
is a void. Any other blank cell makes the generator reject the row, naming it,
rather than skip it. Tricks target follows the source even where one line is
best at every target.

A card's identity comes from the row's content rather than from a hand-typed ID
column, which would be harder to keep consistent. The key and the rules that
keep it stable are in `flashcards/spec.md` #card-identity.

### Holding notation {#holding-notation}

A holding lists its cards from high to low, from `A K Q J T 9` down to `2`:

- **Ten**: `T`. The input file also accepts `10`, which normalizes to `T`.
- **Small cards**: `x` marks a card whose exact rank doesn't matter — it could
  be the lowest spot available without changing the line. A spot card that does
  matter is named, such as `9` or even `4`.
- **Void**: the input file accepts a blank cell, `-`, `v`, `void`, or `(void)`;
  each normalizes to `(void)`.
- **Order**: cards must run high to low. The generator rejects an out-of-order
  holding rather than sorting it.

The normalized holding is part of each card's identity, so changing the
normalization re-mints cards.

### Text formatting {#text-formatting}

The best line and the remarks are Markdown, rendered under the CommonMark
standard, so a list can follow a line of text directly. Google Sheets' own bold
and italics don't survive CSV export, so all formatting comes from the text
itself. Two additions keep the input file free of formatting markup:

- **Line breaks**: a single line break in a cell stays a line break on the card,
  rather than merging into its paragraph.
- **Callouts**: a paragraph opening with a known label, such as `Tip:` or
  `Note:`, is a callout, shown in italics with the label also in bold. The
  labels are a fixed list in code; the input file holds them as plain text.

One departure from CommonMark: HTML typed into a cell shows as plain text rather
than as markup, so a stray `<` can't hide the rest of a cell.

Rendering uses markdown-it-py. Among the Python renderers compared, it alone
passed every example in the CommonMark specification; it ships type information,
has a built-in option for single line breaks, and lets the callout styling act
on parsed tokens rather than patch rendered HTML. Python-Markdown, the most
common choice, is ruled out: it won't start a list directly after a line of
text.

### The card {#suit-combination-card}

One card per row:

- **Front**: a question naming the target, such as "How would you play this suit
  combination for 3 tricks?", then the combination on a line of its own, North's
  holding first, such as `AQTx – J9x`. The target is underlined, so it stands
  out when scanning the card, and each holding shows in its normalized form. Any
  constraints the line assumes, such as limited entries, follow on a line of
  their own.
- **Back**: the line with its percentage, then the remarks, then the source.

The card's styling is the base meant for every note type in the collection, so
all cards look alike:

- **Size and alignment:** Anki's stock 20px, centered.
- **Font:** each platform's own interface font (`system-ui`), such as San
  Francisco on Apple devices.
- **Colors:** none, so cards follow Anki's light and dark themes.

The note type's fields hold the input file's columns, with the holdings stored
in their normalized form. A summary field leads them, such as
`AQT-xx, 2 tricks`; it serves Anki's card browser, and the card doesn't show it.
Searching for `AQT-xx` finds every card for that pair of holdings. The browser
sorts by a single field, so the summary also carries the target: sorting by it
lists each pair's cards in order of target.

Constraints are the exception to fields mirroring columns. The input file gives
each kind of constraint its own column, but a single `Constraints` field holds
them all, written as sentences. Adding an Anki field after the first import
means adding it in Anki first, or a re-import creates a second copy of the note
type, and adding one forces a full sync. Declaring the one field before the
first import lets each kind of constraint arrive later without either step.
Constraints also appear in the summary, each kind in a compact notation of its
own, so cards that share holdings and target stay distinct there.
