# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""The section packer, on hand-built inputs."""

from system_notes import print_layout
from system_notes.print_layout import ColumnPage, WidePage

# --- pack ---

# Heights are in points. Page one's columns run shorter than later pages'
# because the header block owns the top of that page.


def test_two_short_sections_share_page_one_side_by_side() -> None:
  pages = print_layout.pack([30, 30], first_column_height=40, column_height=100)
  assert pages == [ColumnPage(first_column=(0,), second_column=(1,))]


def test_overflowing_page_one_continues_on_a_full_page() -> None:
  pages = print_layout.pack(
    [30, 30, 30], first_column_height=40, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=(1,)),
    ColumnPage(first_column=(2,), second_column=()),
  ]


def test_sections_stack_within_a_column_before_spilling_over() -> None:
  pages = print_layout.pack(
    [30, 50, 40, 70], first_column_height=100, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0, 1), second_column=(2,)),
    ColumnPage(first_column=(3,), second_column=()),
  ]


def test_a_page_splits_its_sections_evenly_between_its_columns() -> None:
  # All three fit the first column, where filling alone would leave them.
  pages = print_layout.pack(
    [30, 30, 30], first_column_height=100, column_height=100
  )
  assert pages == [ColumnPage(first_column=(0, 1), second_column=(2,))]


def test_a_page_closed_early_balances_what_it_already_holds() -> None:
  # The 150-tall section claims a page of its own, so nothing more can join page
  # one; its two sections spread rather than leave a column bare.
  pages = print_layout.pack(
    [20, 20, 150], first_column_height=100, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=(1,)),
    WidePage(section=2),
  ]


def test_a_section_taller_than_page_one_leaves_it_to_the_header() -> None:
  pages = print_layout.pack([90], first_column_height=40, column_height=100)
  assert pages == [
    ColumnPage(first_column=(), second_column=()),
    ColumnPage(first_column=(0,), second_column=()),
  ]


def test_a_section_taller_than_a_column_gets_a_wide_page() -> None:
  pages = print_layout.pack(
    [30, 150, 30], first_column_height=40, column_height=100
  )
  assert pages == [
    ColumnPage(first_column=(0,), second_column=()),
    WidePage(section=1),
    ColumnPage(first_column=(2,), second_column=()),
  ]


def test_a_section_exactly_a_column_tall_still_fits_it() -> None:
  pages = print_layout.pack([40], first_column_height=40, column_height=100)
  assert pages == [ColumnPage(first_column=(0,), second_column=())]
