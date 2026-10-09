# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Building the suit-combination cards as an Anki package.

Reads `flashcards/input/suit_combinations.csv` and writes
`anki/build/suit_combinations.apkg` for Anki's File > Import. Run the script
from the repository root:

```sh
uv run anki/suit_combination_generator.py
```
"""

import html
import sys
from collections.abc import Iterable
from pathlib import Path

import genanki
from markdown_rendering import render_markdown
from suit_combination_note_type import Field, make_note_type
from suit_combination_parsing import SuitCombinationEntry, read_entries

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_INPUT_PATH = _REPOSITORY_ROOT / 'flashcards/input/suit_combinations.csv'
# Gitignored: the committed input file is the record, and the package is rebuilt
# from it.
_OUTPUT_PATH = _REPOSITORY_ROOT / 'anki/build/suit_combinations.apkg'

# Drawn at random once and hard-coded, per genanki's README:
# https://github.com/kerrickstaley/genanki#generating-a-deckpackage
_DECK_ID = 1950376317
_DECK_NAME = 'Bridge::Suit combinations'

# This category's tags, per `flashcards/spec.md` #tag-taxonomy and #categories.
_TAGS = ('cat::suit-combination', 'origin::generated', 'publish::yes')


def build_deck(entries: Iterable[SuitCombinationEntry]) -> genanki.Deck:
  """The deck holding one note per entry."""
  note_type = make_note_type()
  deck = genanki.Deck(deck_id=_DECK_ID, name=_DECK_NAME)
  for entry in entries:
    deck.add_note(_make_note(entry, note_type))
  return deck


def _make_note(
  entry: SuitCombinationEntry, note_type: genanki.Model
) -> genanki.Note:
  """The note for one entry, with each field's value written as HTML."""
  # Most fields do not hold any characters HTML treats specially. Only the free
  # text needs care.
  field_values = {
    Field.SUIT_COMBINATION: _summarize(entry),
    Field.NORTH_HOLDING: str(entry.north),
    Field.SOUTH_HOLDING: str(entry.south),
    Field.TRICKS_TARGET: str(entry.tricks_target),
    # TODO: fill from the constraint columns, as they arrive per
    # `flashcards/tasks.md` #suit-combination-constraints.
    Field.CONSTRAINTS: '',
    Field.SUCCESS_PERCENT: str(entry.success_percent),
    Field.BEST_LINE: render_markdown(entry.best_line),
    Field.REMARKS: render_markdown(entry.remarks),
    Field.SOURCE: html.escape(entry.source, quote=False),
  }
  return genanki.Note(
    model=note_type,
    fields=[field_values[field] for field in Field],
    tags=_TAGS,
    guid=_guid_for(entry),
  )


def _summarize(entry: SuitCombinationEntry) -> str:
  """Both holdings, then the target, such as `AQT-xx, 2 tricks`.

  Sorting by this text groups each pair of holdings, and orders a pair's
  single-digit targets from fewest to most.
  """
  noun = 'trick' if entry.tricks_target == 1 else 'tricks'
  return f'{entry.north}-{entry.south}, {entry.tricks_target} {noun}'


def _guid_for(entry: SuitCombinationEntry) -> str:
  """The note's identity, a frozen contract.

  Read `flashcards/spec.md` #card-identity before changing this function.
  """
  return genanki.guid_for(
    'suit-combination', str(entry.north), str(entry.south), entry.tricks_target
  )


def main() -> None:
  """Build the package from the committed input file."""
  # `utf-8-sig` also reads a file that opens with a byte-order mark, and
  # `newline=''` leaves line breaks inside a cell to the csv module.
  with _INPUT_PATH.open(encoding='utf-8-sig', newline='') as input_file:
    try:
      entries = read_entries(input_file)
    except ValueError as error:
      # The message already lists every invalid row; a traceback adds nothing.
      sys.exit(f'{_INPUT_PATH}: {error}')

  _OUTPUT_PATH.parent.mkdir(exist_ok=True)
  # Leave the package's timestamp at genanki's default, the build time: Anki
  # updates a note on re-import only when the package's copy is newer, so a
  # fixed timestamp would block updates.
  genanki.Package(build_deck(entries)).write_to_file(_OUTPUT_PATH)
  print(f'Wrote {len(entries)} cards to {_OUTPUT_PATH}')


if __name__ == '__main__':
  main()
