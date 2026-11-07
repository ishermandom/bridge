# Fonts

This directory keeps copies of fonts the repo uses or has evaluated, so the
exact files survive even if an upstream copy vanishes or changes.

## Which licenses are allowed

Whether a font may live anywhere in this repository depends on its license:

- **The SIL Open Font License (OFL) is approved**, in
  [version 1.1](https://openfontlicense.org).
- **Other free licenses need careful evaluation first**: a font under another
  free license, such as Apache 2.0, may be adopted only once that license has
  been evaluated and added to this list as approved. A free license lets anyone
  use, modify, and redistribute the font; a font that merely costs nothing does
  not qualify.
- **Non-free licenses are ruled out**: no font under one may be adopted.

A generated document, such as a specimen sheet, may embed subsets of system
fonts under other licenses, as long as each font's license allows that embedding
and the document's distribution. macOS's license defers to each font's own
embedding permission, which Font Book shows.

Each OFL family's folder holds the family's upstream `OFL.txt`, copied verbatim,
because the OFL allows redistribution only as long as the license travels with
every copy. The repository's MIT license does not cover these fonts.

Before adding a font under the OFL:

- **Confirm the license upstream**: check the family's upstream distribution,
  not the font's embedded metadata, which can lag. Roboto Condensed's files
  still name Apache 2.0, for instance, though Google distributes those same
  files under the OFL.
- **Keep the license beside the files**: give the family its own folder, with an
  unchanged copy of the family's upstream `OFL.txt`.
- **Respect reserved font names**: a file changed locally must not carry a name
  its family's `OFL.txt` reserves, and cutting an instance from a variable font
  counts as a change. None of the families cut locally here reserves a name.

## System notes

These files are the fonts `system_notes/notes.css` asks for, and
`system_notes/spec.md #appearance` explains each choice. The renderer doesn't
read them from here: it uses fonts installed on the machine, found through
fontconfig, and `system_notes/Brewfile` installs the same families.

- **IBM Plex Serif** (`ibm-plex/IBMPlexSerif-*.otf`, font version 3.006): the
  `fonts/complete/otf/` directory of the `plex-serif@2.0.0` release zip from
  `github.com/IBM/plex/releases`.
- **Source Sans 3** (`source-sans-3/SourceSans3-{Regular,It,Bold,BoldIt}.ttf`,
  font version 3.052): the `TTF/` directory of the 3.052 release zip from
  `github.com/adobe-fonts/source-sans/releases`. Supplies the few glyphs Plex
  Serif lacks, chiefly the list markers.
- **STIX Two Math** (`stix-two/STIXTwoMath.otf`, font version 2.13 b171):
  `/System/Library/Fonts/Supplemental/` on macOS 15, which ships the same
  version as the latest `github.com/stipub/stixfonts` release. Draws the suit
  symbols.

## Convention cards

These files fall into two groups: candidates for the ACBL renderer's entry text,
and the hand-built HTML card's font stack.
`convention_cards/renderer/spec.md #appearance` records which candidate won, and
`convention_cards/renderer/font_specimen.py` writes a sheet comparing every
candidate to `convention_cards/renderer/specimens/`. The list below is grouped
by where each file came from.

- **Static downloads** (`ibm-plex/IBMPlexSansCondensed-*.ttf`,
  `pt-sans/PTSansNarrow-Regular.ttf`) come straight from
  `github.com/google/fonts`.
- **The HTML card's stack** (`roboto-condensed/RobotoCondensed-variable.ttf`,
  `source-sans-3/SourceSans3-variable.ttf`, and each one's `-Italic-variable`
  partner): the variable releases from `github.com/google/fonts`.
  `convention_cards/renderer/make_two_sided_card.py` embeds them in the page as
  it prints the card, so printing needs no installed fonts.
  `RobotoCondensed-variable.ttf` is also the source the static Roboto Condensed
  cuts below were made from.

  Source Sans 3 is the first family in the stack with suit symbols, so it draws
  the card's suits. The outlined suits reuse those glyphs: the card's CSS gives
  them a white fill and a colored stroke, as the ACBL renderer does. No font
  outside the stack is involved.

- **Google-served static instances** (`google-sans-flex/GoogleSansFlex-*.ttf`,
  all but the Grad100 cut): Google's css2 API serves a true static instance when
  asked for exact axis values:

  ```sh
  curl 'https://fonts.googleapis.com/css2?family=Google+Sans+Flex:opsz,wdth,wght@6,80,500'
  ```

  The response lists one file per width bucket; download the `latin`-coverage
  URL whose internal name matches the request — "6pt Condensed" here, not
  "SemiCondensed". Narrowing barely thins the stems, and locally cut instances
  (next bullet) show the same, so the cause lies in the family's design rather
  than the API.

  The API rounds a `wdth` request (range 25–151) to a named bucket rather than
  serving the exact value: 25 gets "SuperCondensed", 50 "UltraCondensed", and an
  in-between value like 65 gets both neighbors ("ExtraCondensed" and
  "Condensed"). On the standard sample line (`SAMPLE` in `font_specimen.py`) at
  6pt, Medium weight, four of the buckets measure Condensed 255, ExtraCondensed
  245, UltraCondensed 234, and SuperCondensed 212, and the
  `*-{Super,Ultra}Condensed-Medium.ttf` files here are the narrowest two.

  The API silently ignores the GRAD axis (range 0–100), so graded instances must
  be cut locally, as the next bullet describes.

- **Locally instanced Google Sans Flex**
  (`google-sans-flex/GoogleSansFlex-opsz6-SuperCondensed-Grad100.ttf`): cut with
  `fontTools.varLib.instancer` (installed in `~/.venvs/default`) from the
  family's full variable font, the last entry in its download manifest:

  ```sh
  curl 'https://fonts.google.com/download/list?family=Google%20Sans%20Flex'
  ```

  This variable font carries its six public axes on plain `gvar`, with **no avar
  table**, so pinning every axis reproduces the served instances exactly: a
  local `wght=500, wdth=25, opsz=6` cut matches the served SuperCondensed Medium
  on x-height, stem, and sample width. GRAD thickens strokes without widening
  any letter, and GRAD 100 at Regular weight matches Medium's stem exactly, so
  the Grad100 cut has Medium's stroke at Regular's width.

  Each cut gets its own names in name-table entries 1, 4, 6, and 16, because
  reportlab confuses faces that share a name. Entry 6, the PostScript name, may
  not contain spaces or parentheses.

- **Other locally instanced cuts** (`roboto-flex/RobotoFlex-opsz8*.ttf`,
  `roboto-condensed/RobotoCondensed-{Regular,Medium}.ttf`) are cut the same way
  from the `*-variable.ttf` files beside them, renaming included.

  Caveat: Roboto Flex routes width through `avar2` cross-axis mappings, so
  setting its width axis barely narrowed the Roboto Flex cuts: width 25 came out
  only about 7% narrower. `varLib.instancer` applies `avar2` only when **every**
  `fvar` axis is pinned, and raises `NotImplementedError` for a partial pin.
  Full pinning arrived in fontTools 4.59.2 and became correct in 4.61.1, where
  pull request #4002 fixed a double-mapping bug. So pinning every axis with
  fontTools 4.61.1 or later yields a genuinely condensed Roboto Flex, as does
  HarfBuzz's `hb-subset --instance` from 12.3.0 on. The `RobotoFlex-opsz8*.ttf`
  cuts predate that recipe and remain effectively normal-width.

## Measurements for the entry-face decision

A bounding box overstates the stroke of PT Sans Narrow and IBM Plex, whose `l`
has a tail. So the stems below are measured where no tail reaches: render `l` at
1000pt and measure the dark run on a scanline at half the x-height. Both columns
are per point of font size.

| cut                                             | x-height | stem  |
| ----------------------------------------------- | -------- | ----- |
| Google Sans Flex Cond Medium                    | 0.543    | 0.120 |
| Google Sans Flex UltraCond Medium               | 0.543    | 0.118 |
| Google Sans Flex SuperCond Medium               | 0.543    | 0.114 |
| Google Sans Flex SuperCond Grad100              | 0.543    | 0.114 |
| Roboto Condensed Medium                         | 0.528    | 0.114 |
| IBM Plex Condensed Medium                       | 0.520    | 0.103 |
| Avenir Next Cond Medium (system TTC, subfont 5) | 0.502    | 0.086 |
| PT Sans Narrow Regular                          | 0.500    | 0.072 |

Fit is the width of the standard sample line at 6pt; narrower fits more on the
card:

| cut                                | Regular | Medium |
| ---------------------------------- | ------- | ------ |
| PT Sans Narrow                     | 184     |        |
| Avenir Next Condensed              | 187     | 192    |
| Google Sans Flex SuperCond Grad100 | 205     |        |
| Roboto Condensed                   | 209     | 212    |
| Google Sans Flex SuperCond         |         | 212    |
| IBM Plex Condensed                 | 216     | 221    |
| Google Sans Flex UltraCond         |         | 234    |
| Roboto Flex                        | 241     |        |
| Google Sans Flex Cond              | 250     | 255    |

GRAD adds no width by construction: the SuperCondensed Regular sample measures
205 at every grade (0/50/100), while the stem climbs 0.097 → 0.106 → 0.114.
