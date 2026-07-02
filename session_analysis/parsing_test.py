# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the auction and contract parsers.

These pin the interpretation layer: how the vision model's flat strings become
the canonical model, and how unparseable input becomes an issue rather than a
failure. The worked examples in models.md (Parsing) are the oracle.
"""

import pytest

from session_analysis.enums import (
  AnnouncementType,
  CallKind,
  Direction,
  Penalty,
  Rank,
  Strain,
  Suit,
)
from session_analysis.models import (
  Announcement,
  Call,
  Card,
  Contract,
  Passout,
  PlayedContract,
  Result,
)
from session_analysis.parsing import (
  parse_auction,
  parse_contract_cell,
  parse_lead,
)

# --- auction: structural markup ---


def test_circled_call_is_marked_as_by_opponents() -> None:
  (entry,) = parse_auction('(1D)')
  assert entry.by_opponents is True
  assert entry.call == Call(kind=CallKind.BID, level=1, strain=Strain.DIAMONDS)


def test_uncircled_call_is_not_by_opponents() -> None:
  (entry,) = parse_auction('1D')
  assert entry.by_opponents is False


def test_box_flags_its_call_for_discussion() -> None:
  (entry,) = parse_auction('[2N]')
  assert entry.flagged_for_discussion is True
  assert entry.call == Call(kind=CallKind.BID, level=2, strain=Strain.NOTRUMP)


def test_box_spans_several_space_separated_calls() -> None:
  first, second = parse_auction('[2N 3C]')
  assert first.flagged_for_discussion is True
  assert second.flagged_for_discussion is True
  assert second.call == Call(kind=CallKind.BID, level=3, strain=Strain.CLUBS)


def test_box_can_wrap_a_circled_call() -> None:
  (entry,) = parse_auction('[(2C)]')
  assert entry.flagged_for_discussion is True
  assert entry.by_opponents is True
  assert entry.call == Call(kind=CallKind.BID, level=2, strain=Strain.CLUBS)


def test_call_after_the_box_closes_is_not_flagged() -> None:
  # The span ends on `3C]`; the following call sits outside it.
  first, second, third = parse_auction('[2N 3C] 4D')
  assert [e.flagged_for_discussion for e in (first, second, third)] == [
    True,
    True,
    False,
  ]


def test_box_written_with_spaces_still_spans_its_calls() -> None:
  # A bracket set off by spaces arrives as a bare token; it toggles the span
  # without becoming a call of its own.
  entries = parse_auction('[ 2N 3C ]')
  assert len(entries) == 2
  assert all(entry.flagged_for_discussion for entry in entries)


# --- auction: alerts and announcements ---


def test_alert_sets_the_entry_alerted_flag() -> None:
  (entry,) = parse_auction('2H!')
  assert entry.alerted is True
  assert entry.call == Call(kind=CallKind.BID, level=2, strain=Strain.HEARTS)


def test_alert_not_at_the_end_is_flagged_for_review() -> None:
  # `!` is a valid alert only as a trailing mark; elsewhere it isn't an alert,
  # so the call is flagged for a human while the rest still parses best-effort.
  (entry,) = parse_auction('2!H')
  assert entry.alerted is False
  assert entry.issues[0].code == 'misplaced_alert'
  assert entry.call == Call(kind=CallKind.BID, level=2, strain=Strain.HEARTS)


def test_subscript_strain_letter_is_an_artificial_suit_shown() -> None:
  (entry,) = parse_auction('1H_S')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='S',
    type=AnnouncementType.ARTIFICIAL_SUIT,
    shown_strain=Strain.SPADES,
  )


def test_subscript_digit_is_a_minimum_length_in_the_bid_suit() -> None:
  (entry,) = parse_auction('1C_2')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='2',
    type=AnnouncementType.MIN_SUIT_LENGTH,
    suit=Suit.CLUBS,
    minimum_length=2,
  )


def test_semi_forcing_announcement() -> None:
  (entry,) = parse_auction('1N_SF')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='SF', type=AnnouncementType.SEMI_FORCING
  )


def test_forcing_announcement() -> None:
  (entry,) = parse_auction('1N_F')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='F', type=AnnouncementType.FORCING
  )


def test_notrump_range_decodes_to_min_and_max_points() -> None:
  # `^0_2` is 10-12: the teens leading `1` is implied on each digit.
  (entry,) = parse_auction('1N^0_2')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='^0_2',
    type=AnnouncementType.NT_RANGE,
    minimum_points=10,
    maximum_points=12,
  )


@pytest.mark.parametrize('written', ['1N^0_2', '1N_2^0'])
def test_notrump_range_reads_the_same_in_either_marker_order(
  written: str,
) -> None:
  # The superscript floor and subscript ceiling mean the same range whichever
  # order the vision model transcribes them in.
  (entry,) = parse_auction(written)
  assert entry.call is not None
  assert entry.call.announcement is not None
  assert entry.call.announcement.minimum_points == 10
  assert entry.call.announcement.maximum_points == 12


def test_notrump_range_soft_minimum_is_flagged_and_kept_in_raw() -> None:
  # `^4+` is 'a good 14': the floor is 14, flagged soft, and the `+` also
  # survives in raw for a reviewer.
  (entry,) = parse_auction('1N^4+_7')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='^4+_7',
    type=AnnouncementType.NT_RANGE,
    minimum_points=14,
    minimum_points_is_soft=True,
    maximum_points=17,
  )


@pytest.mark.parametrize('written', ['1N^0', '1N^0_2extra', '1N_S^0'])
def test_garbled_notrump_range_degrades_to_other(written: str) -> None:
  # A superscript form missing a half or carrying stray glyphs is a novel form,
  # kept verbatim as `other` rather than misparsed into a range.
  (entry,) = parse_auction(written)
  assert entry.call is not None
  assert entry.call.announcement is not None
  assert entry.call.announcement.type == AnnouncementType.OTHER


def test_unrecognized_announcement_degrades_to_other() -> None:
  # A novel subscript that is neither a strain, a digit, nor a known keyword is
  # kept verbatim rather than failing the call.
  (entry,) = parse_auction('1N_XYZ')
  assert entry.call is not None
  assert entry.call.announcement == Announcement(
    raw='XYZ', type=AnnouncementType.OTHER
  )


# --- auction: notrump spelling ---


@pytest.mark.parametrize('written', ['1N', '1NT'])
def test_notrump_bid_accepts_either_spelling(written: str) -> None:
  # The sheet writes notrump as `N` or `NT`; both mean the same strain.
  (entry,) = parse_auction(written)
  assert entry.call == Call(kind=CallKind.BID, level=1, strain=Strain.NOTRUMP)


# --- auction: pass, double, redouble ---


@pytest.mark.parametrize('written', ['*', 'x', 'X'])
def test_double_may_be_written_as_star_or_x(written: str) -> None:
  (entry,) = parse_auction(written)
  assert entry.call == Call(kind=CallKind.DOUBLE)


@pytest.mark.parametrize('written', ['**', 'xx', 'XX'])
def test_redouble_may_be_written_as_stars_or_x(written: str) -> None:
  (entry,) = parse_auction(written)
  assert entry.call == Call(kind=CallKind.REDOUBLE)


def test_written_pass_is_a_pass_call() -> None:
  (entry,) = parse_auction('p')
  assert entry.call == Call(kind=CallKind.PASS)


# --- auction: unparseable tokens ---


def test_unparseable_call_becomes_an_issue_not_a_failure() -> None:
  (entry,) = parse_auction('ED')
  assert entry.call is None
  assert entry.raw == 'ED'
  assert entry.issues[0].code == 'unparseable_call'


def test_an_unparseable_token_leaves_the_rest_of_the_auction_intact() -> None:
  first, second, third = parse_auction('1H ED 2S')
  assert first.call == Call(kind=CallKind.BID, level=1, strain=Strain.HEARTS)
  assert second.call is None
  assert third.call == Call(kind=CallKind.BID, level=2, strain=Strain.SPADES)


# --- auction: composition and legality ---


def test_parses_a_realistic_competitive_auction() -> None:
  # One line composing the markup the per-feature tests cover in isolation:
  # circles (opponents' calls), an `x` double, an alert, a box, and passes. The
  # bids are rank-legal, so the fixture reads like a real auction.
  entries = parse_auction('1H (x) 2H! (2S) [3H] (p) p')

  assert [e.by_opponents for e in entries] == [
    False,
    True,
    False,
    True,
    False,
    True,
    False,
  ]
  # Only the boxed `[3H]` is flagged for discussion.
  assert [e.flagged_for_discussion for e in entries] == [
    False,
    False,
    False,
    False,
    True,
    False,
    False,
  ]
  assert entries[1].call == Call(kind=CallKind.DOUBLE)  # `(x)`
  assert entries[2].alerted is True  # `2H!`
  assert entries[4].call == Call(
    kind=CallKind.BID, level=3, strain=Strain.HEARTS
  )


def test_parser_does_not_enforce_auction_legality() -> None:
  # `1C` after `1N` is a rank reversal — illegal bridge. Legality is the
  # validation pass's job, so the parser must still parse both cleanly.
  first, second = parse_auction('1N 1C')
  assert first.call == Call(kind=CallKind.BID, level=1, strain=Strain.NOTRUMP)
  assert second.call == Call(kind=CallKind.BID, level=1, strain=Strain.CLUBS)
  assert first.issues == () and second.issues == ()


# --- contract: the standard forms ---


def test_making_contract_parses_to_a_contract_and_result() -> None:
  # No spaces — the vision model won't reliably include them, and the parser
  # tolerates their absence at every seam.
  outcome = parse_contract_cell('2HS+2')
  assert outcome.resolution == PlayedContract(
    contract=Contract(
      level=2,
      strain=Strain.HEARTS,
      declarer=Direction.SOUTH,
      penalty=Penalty.NONE,
    ),
    result=Result(tricks_taken=8),  # `+2` counts up from book (six).
  )


def test_doubled_contract_reads_the_penalty_before_the_declarer() -> None:
  # `6H*W-1`: the `*` between strain and declarer is the penalty; no spaces.
  outcome = parse_contract_cell('6H*W-1')
  played = outcome.resolution
  assert isinstance(played, PlayedContract)
  assert played.contract.penalty == Penalty.DOUBLED
  assert played.contract.declarer == Direction.WEST
  assert played.result.tricks_taken == 11  # 6-level needs 12; down one is 11.


@pytest.mark.parametrize('written', ['6H*W-1', '6HxW-1'])
def test_contract_penalty_may_be_written_as_star_or_x(written: str) -> None:
  # A double may be transcribed `*` or `x`; both read as doubled.
  played = parse_contract_cell(written).resolution
  assert isinstance(played, PlayedContract)
  assert played.contract.penalty == Penalty.DOUBLED


@pytest.mark.parametrize('written', ['3N W +7', '3NT W +7'])
def test_notrump_contract_accepts_either_spelling(written: str) -> None:
  # Notrump is written `N` or `NT` in the contract cell, as in a bid.
  played = parse_contract_cell(written).resolution
  assert isinstance(played, PlayedContract)
  assert played.contract.strain == Strain.NOTRUMP


def test_redoubled_contract_reads_the_double_star() -> None:
  outcome = parse_contract_cell('4S**N+1')
  played = outcome.resolution
  assert isinstance(played, PlayedContract)
  assert played.contract.penalty == Penalty.REDOUBLED


def test_notrump_contract_taking_every_trick() -> None:
  outcome = parse_contract_cell('3N W +7')
  played = outcome.resolution
  assert isinstance(played, PlayedContract)
  assert played.contract.strain == Strain.NOTRUMP
  assert played.result.tricks_taken == 13


@pytest.mark.parametrize(
  'dash',
  [
    chr(0x2D),  # hyphen-minus (ASCII)
    chr(0x2212),  # minus sign
    chr(0x2013),  # en dash
    chr(0x2014),  # em dash
    chr(0x2015),  # horizontal bar
  ],
)
def test_accepts_any_dash_glyph_in_the_result(dash: str) -> None:
  # A set's minus may be transcribed with any dash glyph; all read alike.
  outcome = parse_contract_cell(f'5H S {dash}2')
  played = outcome.resolution
  assert isinstance(played, PlayedContract)
  assert played.result.tricks_taken == 9  # 5-level needs 11; down two.


# --- contract: passout ---


@pytest.mark.parametrize('written', ['PASSOUT', 'PASS', 'ALL PASS', 'all pass'])
def test_pass_in_any_wording_is_a_passout(written: str) -> None:
  # Any cell whose text contains 'pass' is a passout, however it's phrased.
  outcome = parse_contract_cell(written)
  assert isinstance(outcome.resolution, Passout)


@pytest.mark.parametrize(
  'dash',
  [
    chr(0x2D),  # hyphen-minus (ASCII)
    chr(0x2212),  # minus sign
    chr(0x2013),  # en dash
    chr(0x2014),  # em dash
    chr(0x2015),  # horizontal bar
  ],
)
def test_a_cell_struck_through_with_any_dash_is_a_passout(dash: str) -> None:
  # A run of any dash glyph reads as a struck-through, passed-out cell.
  outcome = parse_contract_cell(dash * 3)
  assert isinstance(outcome.resolution, Passout)


# --- contract: unparseable ---


def test_unparseable_contract_becomes_an_issue_not_a_failure() -> None:
  outcome = parse_contract_cell('4?N')
  assert outcome.resolution is None
  assert outcome.raw == '4?N'
  assert outcome.issues[0].code == 'unparseable_contract'


# --- opening lead ---


def test_lead_parses_rank_and_suit() -> None:
  lead = parse_lead('QC')
  assert lead.card == Card(rank=Rank.QUEEN, suit=Suit.CLUBS)
  assert lead.issues == ()


def test_ten_lead_written_as_two_digits_parses() -> None:
  lead = parse_lead('10S')
  assert lead.card == Card(rank=Rank.TEN, suit=Suit.SPADES)


def test_ten_lead_written_as_a_letter_parses() -> None:
  # The sheet may write the ten as `10` or as the rank letter `T`; both read as
  # the same card.
  lead = parse_lead('TH')
  assert lead.card == Card(rank=Rank.TEN, suit=Suit.HEARTS)


def test_lead_surrounding_space_is_ignored() -> None:
  lead = parse_lead(' AD ')
  assert lead.card == Card(rank=Rank.ACE, suit=Suit.DIAMONDS)
  assert lead.raw == ' AD '  # the envelope keeps the verbatim transcription


def test_unparseable_lead_becomes_an_issue_not_a_failure() -> None:
  lead = parse_lead('XZ')
  assert lead.card is None
  assert lead.raw == 'XZ'
  assert lead.issues[0].code == 'unparseable_lead'
