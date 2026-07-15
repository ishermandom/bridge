# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Streamlit app: merge a convention card PDF with a reminders strip.

Upload a convention card PDF (e.g. downloaded from BridgeWinners.com) and paste
bidding reminders, and download a print-ready PDF with the card and a fold-over
reminders strip merged onto one US Letter page. See make_card.make_print_card
for the actual PDF layout logic; this file is only the browser-facing wrapper
around it.
"""

import tempfile
from pathlib import Path

import streamlit as st
from make_card import make_print_card

REMINDERS_HELP = (
  "Lines starting with '#' are section headers. Other lines are bullet "
  "items — a leading '- ' is optional. Wrap text in '**...**' for bold."
)
REMINDERS_PLACEHOLDER = """# Opening bids
- 1NT = 15-17
- **1M 2C** = 2+ clubs, any game force (alertable)
"""

st.set_page_config(page_title='Bridge Convention Card Maker')
st.title('Bridge Convention Card Maker')
st.write(
  'Merges a convention card PDF with a fold-over strip of your own bidding '
  'reminders, producing one print-ready page.'
)

card_file = st.file_uploader('Convention card PDF', type='pdf')
reminders_text = st.text_area(
  'Reminders',
  placeholder=REMINDERS_PLACEHOLDER,
  height=300,
  help=REMINDERS_HELP,
)

if st.button('Generate', disabled=not (card_file and reminders_text)):
  assert card_file is not None  # guaranteed by the disabled= condition above
  with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    card_path = tmp_dir / 'card.pdf'
    reminders_path = tmp_dir / 'reminders.txt'
    output_path = tmp_dir / 'print-ready.pdf'

    card_path.write_bytes(card_file.getvalue())
    reminders_path.write_text(reminders_text, encoding='utf-8')

    make_print_card(card_path, reminders_path, output_path)

    st.download_button(
      'Download print-ready.pdf',
      data=output_path.read_bytes(),
      file_name='print-ready.pdf',
      mime='application/pdf',
    )
