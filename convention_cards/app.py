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

HOW_TO_USE = """
**How to use:**
1. Download your convention card as a PDF — e.g. from
   [BridgeWinners](https://bridgewinners.com/convention-card/).
2. Upload it below.
3. Write your bidding reminders (format guide below the box).
4. Click **Generate**, then download the print-ready PDF.

The output is one US Letter page: your card on the bottom 8.5", your reminders
on the top 2.5" so they fold behind the card and fit comfortably in a card
holder.
"""
REMINDERS_FORMAT_GUIDE = """
**Format:**
- A line starting with a hashtag (`#`) is a section header.
- Other lines are bullet items — a leading hyphen (`- `) is optional.
- Wrap text in double asterisks (`**...**`) for bold.
"""
REMINDERS_EDITOR_NOTE = (
  'Note: The box above may show a red outline and a "press ⌘+Enter to apply" '
  "hint while you type — that's just the text editor. Clicking "
  '**Generate** applies your changes regardless.'
)
REMINDERS_PLACEHOLDER = """Replace this placeholder with your desired reminders:
# Opening bids
- 1NT = 15-17
- **1M 2C** = 2+ clubs, any game force (alertable)
"""

st.set_page_config(page_title='Bridge Convention Card Maker')
st.title('Convention Card Maker')
st.write(
  'Merges a bridge convention card PDF with a fold-over strip of your own '
  'system reminders, producing one print-ready page.'
)
st.markdown(HOW_TO_USE)

card_file = st.file_uploader('Convention card PDF', type='pdf')
reminders_text = st.text_area(
  'Reminders', placeholder=REMINDERS_PLACEHOLDER, height=300
)
st.markdown(REMINDERS_FORMAT_GUIDE)
st.markdown(REMINDERS_EDITOR_NOTE)

if st.button('Generate'):
  if not (card_file and reminders_text):
    st.error('Upload a card PDF and enter reminders first.')
  else:
    with (
      st.spinner('Generating your PDF...'),
      tempfile.TemporaryDirectory() as tmp,
    ):
      tmp_dir = Path(tmp)
      card_path = tmp_dir / 'card.pdf'
      reminders_path = tmp_dir / 'reminders.txt'
      output_path = tmp_dir / 'print-ready.pdf'

      card_path.write_bytes(card_file.getvalue())
      reminders_path.write_text(reminders_text, encoding='utf-8')

      make_print_card(card_path, reminders_path, output_path)
      pdf_bytes = output_path.read_bytes()

    st.download_button(
      'Download print-ready.pdf',
      data=pdf_bytes,
      file_name='print-ready.pdf',
      mime='application/pdf',
    )
