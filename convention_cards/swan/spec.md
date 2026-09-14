# SWAN <-> Bridgodex converters — spec

## Goal

Convert convention cards between BridgeWinners' SWAN export format and the
Bridgodex format in both directions, so a card authored on either site can feed
the ACBL renderer (`../renderer/spec.md`) or be imported into the other site.

## Formats and printed cards

The converters read and write two JSON formats: SWAN (BridgeWinners' export) and
Bridgodex's export. Each site also prints cards in a layout of its own, and
neither layout is the standard printed form, the official ACBL card. The
renderer (`../renderer/spec.md`) exists to print a Bridgodex file on the
official ACBL card.

So the converters take each format's meaning from a different printed card:

- **SWAN from BridgeWinners' card**, the layout SWAN's fields come from.
- **Bridgodex from the official ACBL card**, where the renderer prints Bridgodex
  files. The renderer maps Bridgodex's settings onto the ACBL card's fields, so
  the ACBL card's rules decide what a setting means — most visibly the lead
  charts' bold defaults (#lead-circles). Bridgodex's own printed layout plays no
  part in the conversion: its lead charts bold the same cards as the ACBL
  card's, as a Bridgodex-printed PDF shows, so an uncircled holding means the
  same lead in both.

BridgeWinners' card and the ACBL card agree field for field almost everywhere,
so a single table can link SWAN's fields to Bridgodex's. Where they part ways,
some fields exist in only one format (#mismatched-fields), and the cards' lead
charts give a mark different meanings (#lead-circles).

The ACBL card and BridgeWinners' card also appear as PDFs:

- **The blank ACBL card**: the official fillable form with nothing entered, and
  the renderer's base artwork. Its font data confirms which card of each lead
  holding the form prints in bold (#lead-circles).
- **A pair's BridgeWinners PDF**: that pair's card as BridgeWinners prints it.
  Such PDFs exposed the exporter bugs covered below. The SWAN-to-Bridgodex
  converter can also take one as input, to recover the bold defaults that
  BridgeWinners prints on length holdings but SWAN omits (#lead-circles).

## Core design: one bidirectional table

Both converters derive from a single field-correspondence table
(`swan_mapping.py`), so the two directions cannot drift apart. Each entry links
one Bridgodex setting (`section.key`) to one SWAN path. Entries come in three
kinds, by what the field holds:

- **Check**: Bridgodex `"on"` <-> SWAN `true`. The one checkbox BridgeWinners
  writes as a string can't be linked at all; see the export bugs below.
- **Text**: the same string on both sides, including suit markup such as `!h`
  for ♥, which both formats write the same way.
- **Circle**: the card circled in one lead holding, such as the K in KQx.
  Bridgodex stores its 1-based position; SWAN stores one boolean per card, named
  for the card (`ace_king.king`) or its place (`four_small.fourth`), and the
  table lists those names in holding order. SWAN's names confirm that Bridgodex
  counts positions from 1 at the left, as the renderer assumes.

## BridgeWinners export-bug compensations

Comparing captured cards' BridgeWinners PDFs against their SWAN exports exposed
four bugs in the BridgeWinners exporter, which the table compensates for or
declares one-side-only (each is marked with a comment where the table handles
it):

- **Majors length 4/5 swap**: cards whose PDF shows "5" checked export
  `four: true`, so the table deliberately crosses them: Bridgodex's 5-card
  checkboxes link to SWAN's `four`, and the 4-card ones to `five`.
- **Vs-takeout-double 2NT checkbox swap**: 2NT over the double has four
  checkboxes — natural or raise, over a minor or a major. Two of them trade
  places: SWAN's `nat_majors` carries raise-over-minors, and `raise_minors`
  carries natural-over-majors. The other two checkboxes and the range blanks
  arrive intact.
- **"(Very)Str Open" content dropped**: BridgeWinners' card and the ACBL card
  both have a "(Very)Str Open" blank, but the export omits its content, so
  `other.vs_very_strong` is Bridgodex-only. Though named like that blank, SWAN's
  `vs_strong`/`vs_strong2` keys carry the Other Conventional Calls section's two
  free lines, and the table links them to `other.more1`/`other.more2`.
- **Jump Overcalls "Conv" never exported**: the export writes
  `Overcalls.Jump_overcall.conventional` as `""` whether or not the box is
  ticked, and the import ignores the field — `true`, `"on"`, and `"true"` all
  leave the box unticked. So `overcalls.conv` is Bridgodex-only, the SWAN field
  is SWAN-only and written as `""`, and converting a Bridgodex card that ticks
  the box warns to tick it on BridgeWinners by hand.

BridgeWinners' importer reads the swapped fields the same crossed way: a
generated file imports with the intended boxes checked and the free lines
filled, so the compensations hold in both directions. They mirror BridgeWinners
as observed; if it ever fixes its exporter or importer, each compensation must
be revisited.

## Lead circles versus the bold defaults {#lead-circles}

The ACBL card's lead charts treat two kinds of holding differently. On the honor
and interior holdings (KQx, QJx, KT9x, and the like), the ACBL card prints the
default lead in bold and reserves circles for departures from it ("circle card
led _if not bold_"). On AKx and the length holdings (xx through xxxxx, Hxx
through Hxxxx), it prints no bold. A BridgeWinners mark, by contrast, names the
led card whether or not that card is the default.

Where the ACBL card prints a bold card, the circle link records its position,
verified from the blank ACBL card's font data. SWAN-to-Bridgodex drops a mark at
that position without a warning, since the ACBL card already prints that lead in
bold. Keeping the mark as an explicit circle would be more literal, but the
renderer would then circle a bold card, which the card's "_if not bold_" rules
out. Bridgodex-to-SWAN reads an uncircled holding the way the ACBL card does, as
a lead of its bold card, and marks that card on the SWAN side, so the agreement
stays explicit whatever default BridgeWinners would otherwise show.

On the length holdings, the bold defaults come from BridgeWinners instead: it
bolds a default on each unmarked length holding, computed from the pair's
lead-convention checkboxes. Because the bolds follow those checkboxes, they
differ from card to card, and even between one card's two panels: one captured
card bolds `xxx` at position 3 vs suits but position 1 vs notrump. A fixed table
of bold positions can't capture that, and reproducing the bolds without the PDF
would mean reverse-engineering BridgeWinners' rule for turning checkboxes into
bolds.

So SWAN-to-Bridgodex, given `--synthesize-from-bridgewinners-pdf CARD.pdf`,
reads the bolds from `CARD.pdf`, the BridgeWinners PDF of the card being
converted (see `bridgewinners_lead_bolds.py`). Each unmarked length holding then
converts as if its bold card were circled. An explicit mark always wins over the
PDF's bold, and the converter reports each circle it adds this way; without the
flag, it adds none. In the reverse direction, an uncircled length holding stays
unmarked: the lead-convention checkboxes carry over, and BridgeWinners computes
its bold from them.

## Mismatched fields {#mismatched-fields}

The formats disagree in a handful of places, because BridgeWinners' card differs
from the ACBL card: a few lead holdings differ (BridgeWinners prints AT9x where
the ACBL card prints KT9x), and a few fields are a checkbox on one card but a
text blank on the other. Fields that exist on only one side are declared in
`SWAN_ONLY` / `BRIDGODEX_ONLY`, each with its reason.

Player names are one-side-only for a different reason: BridgeWinners keeps them
outside SWAN. Its export leaves `Overview.names` empty even when the card lists
players, and its import ignores the field, so converting a Bridgodex card with
player names warns that they won't carry over.

- **Unknown fields are a hard error** in both directions, same rationale as the
  renderer: content must never vanish silently. A fuller future export fails
  loudly and the table grows to meet it.
- **Declared one-side-only fields warn** when they carry content (there is
  simply nowhere to put it) and pass silently when unset.
- **Multiple circled cards in one SWAN holding** exceed Bridgodex's capacity
  (one number); conversion keeps the lowest position and warns.

## Output shape

- Bridgodex output: `{"settings": {...}, "notes": ""}`, sections and keys
  sorted, unset fields absent — matching how Bridgodex itself exports.
- SWAN output: every field a BridgeWinners export carries, the SWAN-only ones
  included, since BridgeWinners' import fails on a file that lacks any of them.
  The input's content is applied and everything else is unset (checkboxes
  `false`, text `""`), plus `"New_Format": true` and the bold-card marks from
  #lead-circles.

## Testing

- **Drift guards**: the renderer's full-export fixture doubles as the
  authoritative Bridgodex key list; a test asserts that the mapping plus
  `BRIDGODEX_ONLY` covers that list exactly and that no key or SWAN path is
  mapped twice. A real BridgeWinners export of a test card
  (`testdata/bridgewinners_export.json`) plays the same part for SWAN: the
  Bridgodex-to-SWAN output must carry exactly its fields.
- **Round trip**: the full export, minus its `BRIDGODEX_ONLY` keys, converts to
  SWAN and back unchanged.
- **Behavior tests**: each link kind, each warning path, each hard error.
