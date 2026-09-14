# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""The field-by-field correspondence between SWAN and Bridgodex cards.

SWAN (BridgeWinners' export) nests each section's fields in sub-objects: a
checkbox is a boolean, a blank is free text, and a lead holding is one boolean
per card. Bridgodex keeps each section flat, with values `"on"`, text, or the
circled card's position number. Both converters derive from this one table, so
the two directions cannot drift apart.

Each entry links one Bridgodex setting to one SWAN path. Fields that exist in
only one format are listed in `SWAN_ONLY` / `BRIDGODEX_ONLY` with the reason;
converters warn when such a field carries content, since the other format has
nowhere to put it.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from bridgodex_key import BridgodexKey


@dataclass(frozen=True)
class CheckLink:
  """A checkbox: Bridgodex `"on"` <-> SWAN `true`."""

  bridgodex: BridgodexKey
  swan: tuple[str, ...]


@dataclass(frozen=True)
class TextLink:
  """A free-text blank: the same string on both sides, suit markup included."""

  bridgodex: BridgodexKey
  swan: tuple[str, ...]


@dataclass(frozen=True)
class CircleLink:
  """A lead-chart circle: Bridgodex numeric position <-> SWAN booleans.

  `positions` names the SWAN keys under `swan` in holding order, so index i
  corresponds to Bridgodex position i+1.

  `bold_position` is the 1-based position the ACBL card prints in bold — the
  holding's default lead, verified from the blank card's font data — or None
  where it prints no bold (the AK holdings and all length holdings).

  On the ACBL card, a circle marks a departure from the bold card ("circle card
  led *if not bold*"), while a BridgeWinners mark names the led card whether or
  not it is the default. So SWAN-to-Bridgodex drops a SWAN mark at the bold
  position, and Bridgodex-to-SWAN marks the bold card of an uncircled holding.
  """

  bridgodex: BridgodexKey
  swan: tuple[str, ...]
  positions: tuple[str, ...]
  bold_position: int | None = None


type FieldLink = CheckLink | TextLink | CircleLink


@dataclass(frozen=True)
class SwanOnlyCheck:
  """A SWAN checkbox with no Bridgodex counterpart, and why."""

  swan: tuple[str, ...]
  reason: str


@dataclass(frozen=True)
class SwanOnlyText:
  """A SWAN text blank with no Bridgodex counterpart, and why."""

  swan: tuple[str, ...]
  reason: str


@dataclass(frozen=True)
class SwanOnlyCircle:
  """A SWAN lead holding with no Bridgodex counterpart, and why.

  `positions` names the SWAN keys under `swan` in holding order, as in
  `CircleLink`.
  """

  swan: tuple[str, ...]
  positions: tuple[str, ...]
  reason: str


type SwanOnlyField = SwanOnlyCheck | SwanOnlyText | SwanOnlyCircle


def unset_leaves(
  field: FieldLink | SwanOnlyField,
) -> Mapping[tuple[str, ...], bool | str]:
  """The field's SWAN leaves, each at the value an unset field exports as."""
  match field:
    case CheckLink() | SwanOnlyCheck():
      return {field.swan: False}
    case TextLink() | SwanOnlyText():
      return {field.swan: ''}
    case CircleLink() | SwanOnlyCircle():
      return {(*field.swan, position): False for position in field.positions}


def _bridgodex_key(dotted: str) -> BridgodexKey:
  """Read a Bridgodex setting written as `section.key`."""
  match dotted.split('.'):
    case [section, key]:
      return BridgodexKey(section, key)
    case _:
      raise ValueError(
        f"expected a Bridgodex setting as 'section.key', got {dotted!r}"
      )


def _swan_path(dotted: str) -> tuple[str, ...]:
  """Read a SWAN path written with dots between its levels."""
  return tuple(dotted.split('.'))


def _check(bridgodex: str, swan: str) -> CheckLink:
  """A checkbox row of `MAPPINGS`."""
  return CheckLink(_bridgodex_key(bridgodex), _swan_path(swan))


def _text(bridgodex: str, swan: str) -> TextLink:
  """A free-text row of `MAPPINGS`."""
  return TextLink(_bridgodex_key(bridgodex), _swan_path(swan))


def _circle(
  bridgodex: str,
  swan: str,
  positions: tuple[str, ...],
  bold_position: int | None = None,
) -> CircleLink:
  """A lead-circle row of `MAPPINGS`."""
  return CircleLink(
    _bridgodex_key(bridgodex), _swan_path(swan), positions, bold_position
  )


# Each row gives a Bridgodex setting first, then the SWAN path it maps to.
MAPPINGS: tuple[FieldLink, ...] = (
  # --- overview ---
  _text('overview.general_approach', 'Overview.general_approach'),
  _text('overview.min_exp_hcp_bal_opening', 'Overview.opening_hcp'),
  _text('overview.min_exp_hcp_bal_responding', 'Overview.responding_hcp'),
  _check('overview.forcing_1c', 'Overview.forcing_openings.one_club'),
  _check('overview.forcing_2c', 'Overview.forcing_openings.two_clubs'),
  _check('overview.1nt_open_strong', 'Overview.one_notrump.strong'),
  _check('overview.1nt_open_weak', 'Overview.one_notrump.weak'),
  _check('overview.1nt_open_variable', 'Overview.one_notrump.variable'),
  _text('overview.bids_that_may_require_prep', 'Overview.bids_prep1'),
  _text('overview.more', 'Overview.bids_prep2'),
  # --- other conventional calls ---
  #
  # Despite their names, SWAN's `vs_strong`/`vs_strong2` carry this section's
  # two free lines, and the "(Very) Str Open" blank's own content is missing
  # from the export (observed on a card whose PDF showed all three blanks
  # filled). So `more1`/`more2` link to those keys, and `vs_very_strong` is
  # Bridgodex-only.
  _text('other.jump_shift_resp', 'Other_conventional_calls.jump_shift_resp'),
  _text('other.more1', 'Other_conventional_calls.vs_strong'),
  _text('other.more2', 'Other_conventional_calls.vs_strong2'),
  _check('other.nmf', 'Other_conventional_calls.new_minor_forcing'),
  _check('other.2_way_nmf', 'Other_conventional_calls.two_way'),
  _check('other.xyz', 'Other_conventional_calls.xyz'),
  _check(
    'other.fsf_1rnd', 'Other_conventional_calls.fourth_suit_forcing.one_round'
  ),
  _check(
    'other.fsf_gf', 'Other_conventional_calls.fourth_suit_forcing.to_game'
  ),
  # --- majors ---
  #
  # BridgeWinners' export swaps the four/five length checkboxes: two cards whose
  # PDFs show "5" checked both exported `four: true`. The links below
  # compensate, crossing the names on purpose.
  _check('majors.min_len_1st_2nd_4', 'Majors.first_second.five'),
  _check('majors.min_len_1st_2nd_5', 'Majors.first_second.four'),
  _check('majors.min_len_3rd_4th_4', 'Majors.third_fourth.five'),
  _check('majors.min_len_3rd_4th_5', 'Majors.third_fourth.four'),
  _check('majors.1nt_forcing', 'Majors.one_notrump.forcing'),
  _check('majors.1nt_semi_forcing', 'Majors.one_notrump.semi_forcing'),
  _check('majors.bypass_1_spade', 'Majors.one_notrump.bypass_spades'),
  _check('majors.art_raises_2nt', 'Majors.art_raises.two_notrump'),
  _check('majors.art_raises_3nt', 'Majors.art_raises.three_notrump'),
  _check('majors.art_raises_splinter', 'Majors.art_raises.splinter'),
  _text('majors.art_raises_other', 'Majors.art_raises.art_other'),
  _check('majors.drury_2c', 'Majors.drury.two_clubs'),
  _check('majors.drury_2d', 'Majors.drury.two_diamonds'),
  _check('majors.drury_in_comp', 'Majors.drury.in_comp'),
  _text('majors.drury_other', 'Majors.drury.in_comp_expl'),
  _text('majors.other', 'Majors.major_other1'),
  _text('majors.more', 'Majors.major_other2'),
  _check('majors.jump_raise_weak', 'Majors.jump.weak'),
  _check('majors.jump_raise_mixed', 'Majors.jump.mixed'),
  _check('majors.jump_raise_inv', 'Majors.jump.invitational'),
  _check('majors.jump_raise_overcall_weak', 'Majors.after_overcall.weak'),
  _check('majors.jump_raise_overcall_mixed', 'Majors.after_overcall.mixed'),
  _check(
    'majors.jump_raise_overcall_inv', 'Majors.after_overcall.invitational'
  ),
  # --- minors: 1C ---
  _check('minors.1c_min_len_5', 'Minors.one_club.length.five'),
  _check('minors.1c_min_len_4', 'Minors.one_club.length.four'),
  _check('minors.1c_min_len_3', 'Minors.one_club.length.three'),
  _check('minors.1c_min_len_nf_2', 'Minors.one_club.length.nf2'),
  _check('minors.1c_min_len_nf_2_4432', 'Minors.one_club.length.only_4432'),
  _check('minors.1c_min_len_nf_1', 'Minors.one_club.length.nf1'),
  _check('minors.1c_min_len_nf_0', 'Minors.one_club.length.nf0'),
  _check('minors.1c_min_len_art_f', 'Minors.one_club.length.artf'),
  _text('minors.1c_response', 'Minors.one_club.responses.response1'),
  _text('minors.1c_more', 'Minors.one_club.responses.response2'),
  _check('minors.1c_trans_resp', 'Minors.one_club.responses.transfer_response'),
  _text('minors.1c_1d', 'Minors.one_club.responses.one_diamond'),
  _check(
    'minors.1c_1d_bypass_5', 'Minors.one_club.responses.bypass_five_diamonds'
  ),
  _text('minors.1c_1nt_min', 'Minors.one_club.responses.onent_range_min'),
  _text('minors.1c_1nt_max', 'Minors.one_club.responses.onent_range_max'),
  _text('minors.1c_2nt_min', 'Minors.one_club.responses.twont_range_min'),
  _text('minors.1c_2nt_max', 'Minors.one_club.responses.twont_range_max'),
  _check(
    'minors.1c_single_raise_nf', 'Minors.one_club.raises.single.non_forcing'
  ),
  _check(
    'minors.1c_single_raise_inv', 'Minors.one_club.raises.single.inv_plus'
  ),
  _check(
    'minors.1c_single_raise_gf', 'Minors.one_club.raises.single.game_forcing'
  ),
  _check('minors.1c_jump_raise_weak', 'Minors.one_club.raises.jump.weak'),
  _check('minors.1c_jump_raise_mixed', 'Minors.one_club.raises.jump.mixed'),
  _check(
    'minors.1c_jump_raise_inv', 'Minors.one_club.raises.jump.invitational'
  ),
  _check(
    'minors.1c_jump_raise_overcall_weak',
    'Minors.one_club.raises.after_overcall.weak',
  ),
  _check(
    'minors.1c_jump_raise_overcall_mixed',
    'Minors.one_club.raises.after_overcall.mixed',
  ),
  _check(
    'minors.1c_jump_raise_overcall_inv',
    'Minors.one_club.raises.after_overcall.invitational',
  ),
  # --- minors: 1D ---
  _check('minors.1d_min_len_5', 'Minors.one_diamond.length.five'),
  _check('minors.1d_min_len_4', 'Minors.one_diamond.length.four'),
  _check('minors.1d_min_len_3', 'Minors.one_diamond.length.three'),
  _check('minors.1d_min_len_unbal', 'Minors.one_diamond.length.unbalanced'),
  _check('minors.1d_min_len_nf_2', 'Minors.one_diamond.length.nf2'),
  _check('minors.1d_min_len_nf_1', 'Minors.one_diamond.length.nf1'),
  _check('minors.1d_min_len_nf_0', 'Minors.one_diamond.length.nf0'),
  _check('minors.1d_min_len_art_f', 'Minors.one_diamond.length.artf'),
  _text('minors.1d_response', 'Minors.one_diamond.responses.response1'),
  _text('minors.1d_more', 'Minors.one_diamond.responses.response2'),
  _check('minors.1d_same_as_1c', 'Minors.one_diamond.responses.same_one_club'),
  _text('minors.1d_1nt_min', 'Minors.one_diamond.responses.onent_range_min'),
  _text('minors.1d_1nt_max', 'Minors.one_diamond.responses.onent_range_max'),
  _text('minors.1d_2nt_min', 'Minors.one_diamond.responses.twont_range_min'),
  _text('minors.1d_2nt_max', 'Minors.one_diamond.responses.twont_range_max'),
  _check(
    'minors.1d_single_raise_nf', 'Minors.one_diamond.raises.single.non_forcing'
  ),
  _check(
    'minors.1d_single_raise_inv', 'Minors.one_diamond.raises.single.inv_plus'
  ),
  _check(
    'minors.1d_single_raise_gf', 'Minors.one_diamond.raises.single.game_forcing'
  ),
  _check('minors.1d_jump_raise_weak', 'Minors.one_diamond.raises.jump.weak'),
  _check('minors.1d_jump_raise_mixed', 'Minors.one_diamond.raises.jump.mixed'),
  _check(
    'minors.1d_jump_raise_inv', 'Minors.one_diamond.raises.jump.invitational'
  ),
  _check(
    'minors.1d_jump_raise_overcall_weak',
    'Minors.one_diamond.raises.after_overcall.weak',
  ),
  _check(
    'minors.1d_jump_raise_overcall_mixed',
    'Minors.one_diamond.raises.after_overcall.mixed',
  ),
  _check(
    'minors.1d_jump_raise_overcall_inv',
    'Minors.one_diamond.raises.after_overcall.invitational',
  ),
  # --- 1NT opening ---
  _text(
    '1_no_trump.a_range_min', 'Notrump.one_notrump_opening.range.nt_open_rmin1'
  ),
  _text(
    '1_no_trump.a_range_max', 'Notrump.one_notrump_opening.range.nt_open_rmax1'
  ),
  _text(
    '1_no_trump.a_range_seat_vul', 'Notrump.one_notrump_opening.range.seat_vul'
  ),
  _text(
    '1_no_trump.b_range_min', 'Notrump.one_notrump_opening.range.nt_open_rmin2'
  ),
  _text(
    '1_no_trump.b_range_max', 'Notrump.one_notrump_opening.range.nt_open_rmax2'
  ),
  _check(
    '1_no_trump.b_range_same_resp',
    'Notrump.one_notrump_opening.range.same_response_yes',
  ),
  _check(
    '1_no_trump.5_card_major',
    'Notrump.one_notrump_opening.misc.five_card_major_common',
  ),
  _text('1_no_trump.sys_on_vs', 'Notrump.one_notrump_opening.misc.systems_on'),
  _check(
    '1_no_trump.2c_stayman', 'Notrump.one_notrump_opening.two_clubs.stayman'
  ),
  _check(
    '1_no_trump.2c_puppet',
    'Notrump.one_notrump_opening.two_clubs.puppet_stayman',
  ),
  _check(
    '1_no_trump.2d_nat', 'Notrump.one_notrump_opening.two_diamonds.natural'
  ),
  _check(
    '1_no_trump.2d_tfr', 'Notrump.one_notrump_opening.two_diamonds.transfer'
  ),
  _text(
    '1_no_trump.2d_other', 'Notrump.one_notrump_opening.two_diamonds.other'
  ),
  _check('1_no_trump.2h_nat', 'Notrump.one_notrump_opening.two_hearts.natural'),
  _check(
    '1_no_trump.2h_tfr', 'Notrump.one_notrump_opening.two_hearts.transfer'
  ),
  _text('1_no_trump.2h_other', 'Notrump.one_notrump_opening.two_hearts.other'),
  _check('1_no_trump.2s_nat', 'Notrump.one_notrump_opening.two_spades.natural'),
  _check(
    '1_no_trump.2s_tfr', 'Notrump.one_notrump_opening.two_spades.transfer'
  ),
  _text('1_no_trump.2s_other', 'Notrump.one_notrump_opening.two_spades.other'),
  _check(
    '1_no_trump.2nt_nat', 'Notrump.one_notrump_opening.two_notrump.natural'
  ),
  _check(
    '1_no_trump.2nt_tfr', 'Notrump.one_notrump_opening.two_notrump.transfer'
  ),
  _text(
    '1_no_trump.2nt_other', 'Notrump.one_notrump_opening.two_notrump.other'
  ),
  _check(
    '1_no_trump.smolen', 'Notrump.one_notrump_opening.other_conventions.smolen'
  ),
  _check(
    '1_no_trump.tfr_4c',
    'Notrump.one_notrump_opening.other_conventions.fourC_transfer',
  ),
  _check(
    '1_no_trump.tfr_4d',
    'Notrump.one_notrump_opening.other_conventions.fourD_transfer',
  ),
  _check(
    '1_no_trump.tfr_4h',
    'Notrump.one_notrump_opening.other_conventions.fourH_transfer',
  ),
  _check(
    '1_no_trump.dbl_neg',
    'Notrump.one_notrump_opening.other_conventions.negative_double',
  ),
  _text(
    '1_no_trump.dbl_neg_desc',
    'Notrump.one_notrump_opening.other_conventions.neg_dbl_expl',
  ),
  _check(
    '1_no_trump.dbl_pen',
    'Notrump.one_notrump_opening.other_conventions.penalty_double',
  ),
  # SWAN's name `other_misc` doesn't say which blank it holds; the PDFs of both
  # captured cards show it carries the "Other" blank at the end of the doubles
  # row.
  _text(
    '1_no_trump.dbl_other',
    'Notrump.one_notrump_opening.other_conventions.other_misc',
  ),
  _check(
    '1_no_trump.lebensohl',
    'Notrump.one_notrump_opening.other_conventions.lebensohl.lebensohl',
  ),
  _text(
    '1_no_trump.lebensohl_desc',
    'Notrump.one_notrump_opening.other_conventions.lebensohl.leb_expl',
  ),
  _text('1_no_trump.3c', 'Notrump.one_notrump_opening.three_clubs'),
  _text('1_no_trump.3d', 'Notrump.one_notrump_opening.three_diamonds'),
  _text('1_no_trump.3h', 'Notrump.one_notrump_opening.three_hearts'),
  _text('1_no_trump.3s', 'Notrump.one_notrump_opening.three_spades'),
  _text('1_no_trump.other', 'Notrump.one_notrump_opening.other.other1'),
  _text('1_no_trump.more', 'Notrump.one_notrump_opening.other.other2'),
  # --- 2NT / 3NT openings ---
  _text('2_no_trump.range_min', 'Notrump.two_notrump_opening.twont_open_min'),
  _text('2_no_trump.range_max', 'Notrump.two_notrump_opening.twont_open_max'),
  _check('2_no_trump.puppet', 'Notrump.two_notrump_opening.puppet'),
  _check('2_no_trump.3s', 'Notrump.two_notrump_opening.three_spades'),
  _text('2_no_trump.3s_desc', 'Notrump.two_notrump_opening.three_spades_expl'),
  _check('2_no_trump.conv', 'Notrump.two_notrump_opening.conventional'),
  _text('2_no_trump.conv_desc', 'Notrump.two_notrump_opening.conv_explanation'),
  _check(
    '2_no_trump.tfr_3lvl', 'Notrump.two_notrump_opening.transfer.three_level'
  ),
  _check(
    '2_no_trump.tfr_4lvl', 'Notrump.two_notrump_opening.transfer.four_level'
  ),
  _check('2_no_trump.neg_dbl', 'Notrump.two_notrump_opening.negative_doubles'),
  _text('2_no_trump.other', 'Notrump.two_notrump_opening.other'),
  _text(
    '3_no_trump.range_min', 'Notrump.three_notrump_opening.threent_open_min'
  ),
  _text(
    '3_no_trump.range_max', 'Notrump.three_notrump_opening.threent_open_max'
  ),
  _check('3_no_trump.one_suit', 'Notrump.three_notrump_opening.one_suit'),
  _text(
    '3_no_trump.one_suit_desc', 'Notrump.three_notrump_opening.one_suit_expl'
  ),
  # --- two-level openings ---
  _text('two_level.2c_min', 'Two_level.two_clubs.twoC_range_min'),
  _text('two_level.2c_max', 'Two_level.two_clubs.twoC_range_max'),
  _text('two_level.2c_range_desc', 'Two_level.two_clubs.twoC_expl'),
  _check('two_level.2c_2d_neg', 'Two_level.two_clubs.two_diamonds.negative'),
  _check('two_level.2c_2d_waiting', 'Two_level.two_clubs.two_diamonds.waiting'),
  _check('two_level.2c_steps', 'Two_level.two_clubs.steps'),
  _text('two_level.2c_steps_desc', 'Two_level.two_clubs.steps_expl'),
  _check('two_level.2c_2h_neg', 'Two_level.two_clubs.twoH_neg'),
  _check('two_level.2c_very_str', 'Two_level.two_clubs.very_strong'),
  _check('two_level.2c_str', 'Two_level.two_clubs.strong'),
  _check('two_level.2c_nat', 'Two_level.two_clubs.natural'),
  _check('two_level.2c_conv', 'Two_level.two_clubs.conventional'),
  _text('two_level.2c_conv_desc', 'Two_level.two_clubs.conv_explanation'),
  _text('two_level.2c_other', 'Two_level.two_clubs.twoC_other'),
  _text('two_level.2d_min', 'Two_level.two_diamonds.twoD_range_min'),
  _text('two_level.2d_max', 'Two_level.two_diamonds.twoD_range_max'),
  _text('two_level.2d_desc', 'Two_level.two_diamonds.twoD_expl'),
  _check('two_level.2d_weak', 'Two_level.two_diamonds.weak'),
  _check('two_level.2d_int', 'Two_level.two_diamonds.intermediate'),
  _check('two_level.2d_str', 'Two_level.two_diamonds.strong'),
  _check('two_level.2d_conv', 'Two_level.two_diamonds.conventional'),
  _check('two_level.2d_nsnf', 'Two_level.two_diamonds.new_suit_non_forcing'),
  _text('two_level.2d_rebids_2nt', 'Two_level.two_diamonds.rebid_over_2nt'),
  _text('two_level.2d_other', 'Two_level.two_diamonds.twoD_other'),
  _text('two_level.2h_min', 'Two_level.two_hearts.twoH_range_min'),
  _text('two_level.2h_max', 'Two_level.two_hearts.twoH_range_max'),
  _text('two_level.2h_desc', 'Two_level.two_hearts.twoH_expl'),
  _check('two_level.2h_weak', 'Two_level.two_hearts.weak'),
  _check('two_level.2h_int', 'Two_level.two_hearts.intermediate'),
  _check('two_level.2h_str', 'Two_level.two_hearts.strong'),
  _check('two_level.2h_nsnf', 'Two_level.two_hearts.new_suit_non_forcing'),
  _text('two_level.2h_rebids_2nt', 'Two_level.two_hearts.rebid_over_2nt'),
  _text('two_level.2h_other', 'Two_level.two_hearts.twoH_other'),
  _text('two_level.2s_min', 'Two_level.two_spades.twoS_range_min'),
  _text('two_level.2s_max', 'Two_level.two_spades.twoS_range_max'),
  _text('two_level.2s_desc', 'Two_level.two_spades.twoS_expl'),
  _check('two_level.2s_weak', 'Two_level.two_spades.weak'),
  _check('two_level.2s_int', 'Two_level.two_spades.intermediate'),
  _check('two_level.2s_str', 'Two_level.two_spades.strong'),
  _check('two_level.2s_nsnf', 'Two_level.two_spades.new_suit_non_forcing'),
  _text('two_level.2s_rebids_2nt', 'Two_level.two_spades.rebid_over_2nt'),
  _text('two_level.2s_other', 'Two_level.two_spades.twoS_other'),
  # --- doubles ---
  _check('doubles.negative', 'Doubles.negative_doubles.negative'),
  _text('doubles.negative_thru', 'Doubles.negative_doubles.through'),
  _check('doubles.penalty', 'Doubles.penalty'),
  _check('doubles.responsive', 'Doubles.responsive_doubles.responsive'),
  _text('doubles.responsive_thru', 'Doubles.responsive_doubles.through'),
  _check('doubles.maximal', 'Doubles.responsive_doubles.maximal_doubles'),
  _check('doubles.support', 'Doubles.support_doubles.support'),
  _text('doubles.support_thru', 'Doubles.support_doubles.through'),
  _check('doubles.support_rdbl', 'Doubles.support_doubles.support_redoubles'),
  _text('doubles.to_style', 'Doubles.takeout_style'),
  _text('doubles.other', 'Doubles.dbl_exp'),
  # --- notrump overcalls ---
  _text(
    'nt_overcalls.direct_1nt_min', 'Notrump_overcalls.direct.nt_overcall_rmin'
  ),
  _text(
    'nt_overcalls.direct_1nt_max', 'Notrump_overcalls.direct.nt_overcall_rmax'
  ),
  _check(
    'nt_overcalls.direct_systems_on', 'Notrump_overcalls.direct.systems_on'
  ),
  _text(
    'nt_overcalls.balance_1nt_min', 'Notrump_overcalls.balance.bal_nt_rmin'
  ),
  _text(
    'nt_overcalls.balance_1nt_max', 'Notrump_overcalls.balance.bal_nt_rmax'
  ),
  _check(
    'nt_overcalls.balance_systems_on', 'Notrump_overcalls.balance.systems_on'
  ),
  _check('nt_overcalls.conv', 'Notrump_overcalls.conventional'),
  _text('nt_overcalls.conv_desc', 'Notrump_overcalls.conv_expl'),
  _check(
    'nt_overcalls.jump_2nt_2_lowest_unbid',
    'Notrump_overcalls.jump_two_notrump_overcalls.two_lowest',
  ),
  _text(
    'nt_overcalls.other', 'Notrump_overcalls.jump_two_notrump_overcalls.other'
  ),
  # --- overcalls ---
  _text('overcalls.1_lvl_min', 'Overcalls.one_level_range_min'),
  _text('overcalls.1_lvl_max', 'Overcalls.one_level_range_max'),
  _check('overcalls.1_lvl_4cards', 'Overcalls.often_four'),
  _text('overcalls.2_lvl_min', 'Overcalls.two_level_range_min'),
  _text('overcalls.2_lvl_max', 'Overcalls.two_level_range_max'),
  _check('overcalls.jump_weak', 'Overcalls.Jump_overcall.weak'),
  _check('overcalls.jump_int', 'Overcalls.Jump_overcall.intermediate'),
  _check('overcalls.jump_strong', 'Overcalls.Jump_overcall.strong'),
  _text('overcalls.conv_desc', 'Overcalls.Jump_overcall.conv_expl'),
  _check('overcalls.new_suit_forcing', 'Overcalls.responses.new_suit.forcing'),
  _check(
    'overcalls.new_suit_nf_const',
    'Overcalls.responses.new_suit.non_forcing_constructive',
  ),
  _check('overcalls.new_suit_nf', 'Overcalls.responses.new_suit.non_forcing'),
  _check('overcalls.new_suit_tfr', 'Overcalls.responses.new_suit.transfer'),
  _check('overcalls.jump_raise_wk', 'Overcalls.responses.jump_raise.weak'),
  _check('overcalls.jump_raise_mixed', 'Overcalls.responses.jump_raise.mixed'),
  _check(
    'overcalls.jump_raise_inv', 'Overcalls.responses.jump_raise.invitational'
  ),
  _text('overcalls.cuebids', 'Overcalls.responses.cuebids'),
  _check('overcalls.cue_support', 'Overcalls.responses.support'),
  _text('overcalls.other', 'Overcalls.oc_other'),
  # --- direct cuebids ---
  _check(
    'direct_cuebids.art_michaels', 'Direct_cuebids.vs_art_minors.michaels'
  ),
  _check('direct_cuebids.art_natural', 'Direct_cuebids.vs_art_minors.natural'),
  _check('direct_cuebids.art_other', 'Direct_cuebids.vs_art_minors.other'),
  _check(
    'direct_cuebids.quasi_michaels', 'Direct_cuebids.vs_quasi_minors.michaels'
  ),
  _check(
    'direct_cuebids.quasi_natural', 'Direct_cuebids.vs_quasi_minors.natural'
  ),
  _check('direct_cuebids.quasi_other', 'Direct_cuebids.vs_quasi_minors.other'),
  _check(
    'direct_cuebids.nat_minors_michaels',
    'Direct_cuebids.vs_nat_minors.michaels',
  ),
  _check(
    'direct_cuebids.nat_minors_natural', 'Direct_cuebids.vs_nat_minors.natural'
  ),
  _check(
    'direct_cuebids.nat_minors_other', 'Direct_cuebids.vs_nat_minors.other'
  ),
  _check(
    'direct_cuebids.nat_majors_michaels',
    'Direct_cuebids.vs_nat_majors.michaels',
  ),
  _check(
    'direct_cuebids.nat_majors_natural', 'Direct_cuebids.vs_nat_majors.natural'
  ),
  _check(
    'direct_cuebids.nat_majors_other', 'Direct_cuebids.vs_nat_majors.other'
  ),
  _text('direct_cuebids.describe', 'Direct_cuebids.cue_describe'),
  # --- vs 1NT opening ---
  _text('vs_1nt_opening.vs_a', 'Vs_notrump.versus.vs1'),
  _text('vs_1nt_opening.vs_b', 'Vs_notrump.versus.vs2'),
  _text('vs_1nt_opening.vs_a_dbl', 'Vs_notrump.double.double1'),
  _text('vs_1nt_opening.vs_b_dbl', 'Vs_notrump.double.double2'),
  _text('vs_1nt_opening.vs_a_2c', 'Vs_notrump.two_clubs.twoC1'),
  _text('vs_1nt_opening.vs_b_2c', 'Vs_notrump.two_clubs.twoC2'),
  _text('vs_1nt_opening.vs_a_2d', 'Vs_notrump.two_diamonds.twoD1'),
  _text('vs_1nt_opening.vs_b_2d', 'Vs_notrump.two_diamonds.twoD2'),
  _text('vs_1nt_opening.vs_a_2h', 'Vs_notrump.two_hearts.twoH1'),
  _text('vs_1nt_opening.vs_b_2h', 'Vs_notrump.two_hearts.twoH2'),
  _text('vs_1nt_opening.vs_a_2s', 'Vs_notrump.two_spades.twoS1'),
  _text('vs_1nt_opening.vs_b_2s', 'Vs_notrump.two_spades.twoS2'),
  _text('vs_1nt_opening.vs_a_2nt', 'Vs_notrump.two_NT.twoNT1'),
  _text('vs_1nt_opening.vs_b_2nt', 'Vs_notrump.two_NT.twoNT2'),
  _text('vs_1nt_opening.other', 'Vs_notrump.nt_def_other'),
  # --- vs takeout double ---
  _check(
    'vs_to_double.new_suit_forcing_2_lvl',
    'Vs_takeout_double.new_suit_forcing.two_level',
  ),
  _check(
    'vs_to_double.new_suit_forcing_transfer',
    'Vs_takeout_double.new_suit_forcing.transfer',
  ),
  _text(
    'vs_to_double.new_suit_forcing_transfer_desc',
    'Vs_takeout_double.new_suit_forcing.tfr_expl',
  ),
  _check('vs_to_double.jump_shift_weak', 'Vs_takeout_double.jump_shift.weak'),
  _check(
    'vs_to_double.jump_shift_inv', 'Vs_takeout_double.jump_shift.invitational'
  ),
  _check('vs_to_double.jump_shift_f', 'Vs_takeout_double.jump_shift.forcing'),
  _check('vs_to_double.jump_shift_fit', 'Vs_takeout_double.jump_shift.fit'),
  _check('vs_to_double.redouble_10_plus', 'Vs_takeout_double.redouble_10'),
  _check('vs_to_double.redouble_conv', 'Vs_takeout_double.conventional'),
  _text('vs_to_double.redouble_conv_desc', 'Vs_takeout_double.conv_expl'),
  # BridgeWinners' export swaps two of the four 2NT checkboxes: a card whose PDF
  # showed raise-over-minors checked exported `nat_majors: true`, and
  # natural-over-majors arrives as `raise_minors: true`. The other two
  # checkboxes and the range blanks arrive intact. The links for
  # `2nt_over_minors_raise` and `2nt_over_majors_nat` cross to compensate.
  _check(
    'vs_to_double.2nt_over_minors_nat',
    'Vs_takeout_double.two_notrump_over.nat_minors',
  ),
  _check(
    'vs_to_double.2nt_over_minors_raise',
    'Vs_takeout_double.two_notrump_over.nat_majors',
  ),
  _text(
    'vs_to_double.2nt_over_minors_min',
    'Vs_takeout_double.two_notrump_over.rmin_minors',
  ),
  _text(
    'vs_to_double.2nt_over_minors_max',
    'Vs_takeout_double.two_notrump_over.rmax_minors',
  ),
  _check(
    'vs_to_double.2nt_over_majors_nat',
    'Vs_takeout_double.two_notrump_over.raise_minors',
  ),
  _check(
    'vs_to_double.2nt_over_majors_raise',
    'Vs_takeout_double.two_notrump_over.raise_majors',
  ),
  _text(
    'vs_to_double.2nt_over_majors_min',
    'Vs_takeout_double.two_notrump_over.rmin_majors',
  ),
  _text(
    'vs_to_double.2nt_over_majors_max',
    'Vs_takeout_double.two_notrump_over.rmax_majors',
  ),
  _text('vs_to_double.other', 'Vs_takeout_double.vs_takeout_other'),
  # --- vs preempts ---
  _text('vs_preempts.2nt_overcall', 'Vs_preempts.twoNT_overcall'),
  _text('vs_preempts.to_dbl_thru', 'Vs_preempts.takeout_through'),
  _check('vs_preempts.to_dbl_penalty', 'Vs_preempts.penalty'),
  _check('vs_preempts.2nt_lebensohl_resp', 'Vs_preempts.leb_2NT'),
  _text('vs_preempts.2nt_lebensohl_resp_desc', 'Vs_preempts.leb_expl'),
  _text('vs_preempts.cuebid', 'Vs_preempts.cuebid'),
  _text('vs_preempts.jump_overcalls', 'Vs_preempts.jump_overcalls'),
  _text('vs_preempts.other', 'Vs_preempts.vs_preempt_other'),
  # --- preempts ---
  _text('preempts.3_lvl_style', 'Preempts.three_level_style1'),
  _text('preempts.3_lvl_more', 'Preempts.three_level_style2'),
  _text('preempts.3_lvl_resp', 'Preempts.three_level_response'),
  _text('preempts.4_lvl_style', 'Preempts.four_level_style'),
  _text('preempts.4_lvl_resp', 'Preempts.four_level_response'),
  _check('preempts.4_lvl_minors_transfer', 'Preempts.fourCD_transfer'),
  _text('preempts.4_lvl_other', 'Preempts.preempts_other'),
  # --- slams ---
  _check('slams.gerber_directly_over_nt', 'Slams.gerber.directlyNT'),
  _check('slams.gerber_over_nt_seq', 'Slams.gerber.seq_NT'),
  _check('slams.gerber_over_non_nt_seq', 'Slams.gerber.non_seq_NT'),
  _text('slams.gerber_other', 'Slams.gerber.gerber_expl'),
  _check('slams.4nt_blackwood', 'Slams.fourNT.blackwood'),
  _check('slams.4nt_rkc_0314', 'Slams.fourNT.rkc_0314'),
  _check('slams.4nt_rkc_1430', 'Slams.fourNT.rkc_1430'),
  _text('slams.4nt_more', 'Slams.fourNT.fourNT_expl'),
  _text('slams.control_bids', 'Slams.control_bids'),
  _text('slams.vs_interference', 'Slams.vs_interference'),
  _text('slams.other', 'Slams.slams_other'),
  # --- carding ---
  _check('carding.suits_std_att', 'Carding.suits.standard_attitude'),
  _check('carding.suits_std_count', 'Carding.suits.standard_count'),
  _check('carding.suits_ud_att', 'Carding.suits.upside_down_attitude'),
  _check('carding.suits_ud_count', 'Carding.suits.upside_down_count'),
  _check('carding.nt_std_att', 'Carding.notrump.standard_attitude'),
  _check('carding.nt_std_count', 'Carding.notrump.standard_count'),
  _check('carding.nt_ud_att', 'Carding.notrump.upside_down_attitude'),
  _check('carding.nt_ud_count', 'Carding.notrump.upside_down_count'),
  _text('carding.exceptions', 'Carding.exceptions'),
  _text('carding.other', 'Carding.other_carding'),
  _check('carding.smith_echo_suits', 'Carding.smith.smith_suits'),
  _check('carding.smith_echo_nt', 'Carding.smith.smith_NT'),
  _check('carding.smith_echo_reverse', 'Carding.smith.reverse_smith'),
  _text('carding.trump_signals', 'Carding.trump_signals'),
  # --- signals ---
  _check('signals.declarer_lead_att', 'Signals.declarer_lead.attitude'),
  _check('signals.declarer_lead_count', 'Signals.declarer_lead.count'),
  _check('signals.declarer_lead_pref', 'Signals.declarer_lead.suit_pref'),
  _check('signals.partner_lead_att', 'Signals.partner_lead.attitude'),
  _check('signals.partner_lead_count', 'Signals.partner_lead.count'),
  _check('signals.partner_lead_pref', 'Signals.partner_lead.suit_pref'),
  _text('signals.exceptions', 'Signals.exceptions'),
  _check('signals.first_discard_std', 'Signals.first_discard.standard'),
  _check('signals.first_discard_ud', 'Signals.first_discard.upside_down'),
  _check('signals.lavinthal', 'Signals.first_discard.lavinthal'),
  _check('signals.odd_even', 'Signals.first_discard.odd_even'),
  _check('signals.other', 'Signals.first_discard.other'),
  _text('signals.other1', 'Signals.signals_other1'),
  _text('signals.other2', 'Signals.signals_other2'),
  # --- leads vs suits ---
  _check('leads_vs_suits.length_4th', 'Leads_vs_suits.length_leads.fourth'),
  _check(
    'leads_vs_suits.length_3rd_5th', 'Leads_vs_suits.length_leads.third_fifth'
  ),
  _check(
    'leads_vs_suits.length_3rd_low', 'Leads_vs_suits.length_leads.third_low'
  ),
  _check('leads_vs_suits.attitude', 'Leads_vs_suits.length_leads.attitude'),
  _check(
    'leads_vs_suits.small_from_xx', 'Leads_vs_suits.length_leads.small_from_xx'
  ),
  _text('leads_vs_suits.after_1st_trick', 'Leads_vs_suits.after_first_trick'),
  _check(
    'leads_vs_suits.honor_leads_akx_varies',
    'Leads_vs_suits.honor_leads.ace_king.varies',
  ),
  _text(
    'leads_vs_suits.honor_leads_akx_varies_desc',
    'Leads_vs_suits.honor_leads.ace_king.varies_expl',
  ),
  _text('leads_vs_suits.exceptions', 'Leads_vs_suits.exceptions'),
  _circle(
    'leads_vs_suits.length_leads_xx',
    'Leads_vs_suits.length_leads.doubleton',
    ('first', 'second'),
  ),
  _circle(
    'leads_vs_suits.length_leads_xxx',
    'Leads_vs_suits.length_leads.tripleton',
    ('first', 'second', 'third'),
  ),
  _circle(
    'leads_vs_suits.length_leads_xxxx',
    'Leads_vs_suits.length_leads.four_small',
    ('first', 'second', 'third', 'fourth'),
  ),
  _circle(
    'leads_vs_suits.length_leads_xxxxx',
    'Leads_vs_suits.length_leads.five_small',
    ('first', 'second', 'third', 'fourth', 'fifth'),
  ),
  _circle(
    'leads_vs_suits.length_leads_Hxx',
    'Leads_vs_suits.length_leads.Hxx',
    ('first', 'second', 'third'),
  ),
  _circle(
    'leads_vs_suits.length_leads_Hxxx',
    'Leads_vs_suits.length_leads.Hxxx',
    ('first', 'second', 'third', 'fourth'),
  ),
  _circle(
    'leads_vs_suits.length_leads_Hxxxx',
    'Leads_vs_suits.length_leads.Hxxxx',
    ('first', 'second', 'third', 'fourth', 'fifth'),
  ),
  _circle(
    'leads_vs_suits.honor_leads_AKx',
    'Leads_vs_suits.honor_leads.ace_king',
    ('ace', 'king', 'low'),
  ),
  _circle(
    'leads_vs_suits.honor_leads_KQx',
    'Leads_vs_suits.honor_leads.king_queen',
    ('king', 'queen', 'low'),
    bold_position=1,
  ),
  _circle(
    'leads_vs_suits.honor_leads_QJx',
    'Leads_vs_suits.honor_leads.queen_jack',
    ('queen', 'jack', 'low'),
    bold_position=1,
  ),
  # BridgeWinners prints this holding as JT9 where the ACBL card prints JTx; the
  # three positions still line up one for one.
  _circle(
    'leads_vs_suits.honor_leads_JTx',
    'Leads_vs_suits.honor_leads.jack_ten',
    ('jack', 'ten', 'nine'),
    bold_position=1,
  ),
  _circle(
    'leads_vs_suits.honor_interior_seq_KJTx',
    'Leads_vs_suits.interior_seq.king_jack_ten',
    ('king', 'jack', 'ten', 'low'),
    bold_position=2,
  ),
  _circle(
    'leads_vs_suits.honor_interior_seq_KT9x',
    'Leads_vs_suits.interior_seq.king_ten_nine',
    ('king', 'ten', 'nine', 'low'),
    bold_position=2,
  ),
  _circle(
    'leads_vs_suits.honor_interior_seq_QT9x',
    'Leads_vs_suits.interior_seq.queen_ten_nine',
    ('queen', 'ten', 'nine', 'low'),
    bold_position=2,
  ),
  # --- leads vs notrump ---
  _check('leads_vs_nt.length_4th', 'Leads_vs_notrump.length_leads.fourth'),
  _check(
    'leads_vs_nt.length_3rd_5th', 'Leads_vs_notrump.length_leads.third_fifth'
  ),
  _check(
    'leads_vs_nt.length_3rd_low', 'Leads_vs_notrump.length_leads.third_low'
  ),
  _check('leads_vs_nt.attitude', 'Leads_vs_notrump.length_leads.attitude'),
  _check(
    'leads_vs_nt.second_from_xxxxn',
    'Leads_vs_notrump.length_leads.second_from_xxxx',
  ),
  _text('leads_vs_nt.after_1st_trick', 'Leads_vs_notrump.after_first_trick'),
  _check(
    'leads_vs_nt.honor_leads_akx_varies',
    'Leads_vs_notrump.honor_leads.ace_king.varies',
  ),
  _text(
    'leads_vs_nt.honor_leads_akx_varies_desc',
    'Leads_vs_notrump.honor_leads.ace_king.varies_expl',
  ),
  _text('leads_vs_nt.exceptions', 'Leads_vs_notrump.exceptions'),
  _circle(
    'leads_vs_nt.length_leads_xx',
    'Leads_vs_notrump.length_leads.doubleton',
    ('first', 'second'),
  ),
  _circle(
    'leads_vs_nt.length_leads_xxx',
    'Leads_vs_notrump.length_leads.tripleton',
    ('first', 'second', 'third'),
  ),
  _circle(
    'leads_vs_nt.length_leads_xxxx',
    'Leads_vs_notrump.length_leads.four_small',
    ('first', 'second', 'third', 'fourth'),
  ),
  _circle(
    'leads_vs_nt.length_leads_xxxxx',
    'Leads_vs_notrump.length_leads.five_small',
    ('first', 'second', 'third', 'fourth', 'fifth'),
  ),
  _circle(
    'leads_vs_nt.length_leads_Hxx',
    'Leads_vs_notrump.length_leads.Hxx',
    ('first', 'second', 'third'),
  ),
  _circle(
    'leads_vs_nt.length_leads_Hxxx',
    'Leads_vs_notrump.length_leads.Hxxx',
    ('first', 'second', 'third', 'fourth'),
  ),
  _circle(
    'leads_vs_nt.length_leads_Hxxxx',
    'Leads_vs_notrump.length_leads.Hxxxx',
    ('first', 'second', 'third', 'fourth', 'fifth'),
  ),
  _circle(
    'leads_vs_nt.honor_leads_AKxx',
    'Leads_vs_notrump.honor_leads.ace_king',
    ('ace', 'king', 'low1', 'low2'),
  ),
  _circle(
    'leads_vs_nt.honor_leads_KQJx',
    'Leads_vs_notrump.honor_leads.king_queen_jack',
    ('king', 'queen', 'jack', 'low'),
    bold_position=1,
  ),
  _circle(
    'leads_vs_nt.honor_leads_KQT9',
    'Leads_vs_notrump.honor_leads.king_queen_ten_nine',
    ('king', 'queen', 'ten', 'nine'),
    bold_position=2,
  ),
  _circle(
    'leads_vs_nt.honor_leads_QJTx',
    'Leads_vs_notrump.honor_leads.queen_jack_ten',
    ('queen', 'jack', 'ten', 'low'),
    bold_position=1,
  ),
  _circle(
    'leads_vs_nt.honor_leads_JT9x',
    'Leads_vs_notrump.honor_leads.jack_ten_nine',
    ('jack', 'ten', 'nine', 'low'),
    bold_position=1,
  ),
  _circle(
    'leads_vs_nt.honor_interior_seq_AQJx',
    'Leads_vs_notrump.interior_seq.ace_queen_jack',
    ('ace', 'queen', 'jack', 'low'),
    bold_position=2,
  ),
  _circle(
    'leads_vs_nt.honor_interior_seq_AJTx',
    'Leads_vs_notrump.interior_seq.ace_jack_ten',
    ('ace', 'jack', 'ten', 'low'),
    bold_position=2,
  ),
  _circle(
    'leads_vs_nt.honor_interior_seq_QT9x',
    'Leads_vs_notrump.interior_seq.queen_ten_nine',
    ('queen', 'ten', 'nine', 'low'),
    bold_position=2,
  ),
)

# SWAN fields with no Bridgodex counterpart, and why. Conversion warns when one
# carries content, and Bridgodex-to-SWAN still writes each one unset, since
# BridgeWinners' import fails on a file that lacks any of them.
SWAN_ONLY: tuple[SwanOnlyField, ...] = (
  SwanOnlyText(
    _swan_path('Overview.names'),
    'BridgeWinners keeps player names outside SWAN: its export leaves this'
    ' field empty, and its import ignores it',
  ),
  SwanOnlyCheck(
    _swan_path('Overview.forcing_openings.other'),
    'Bridgodex records the Forcing Openings "Other" field as text'
    ' (overview.forcing_other) and SWAN as a checkbox, so neither value fits'
    ' the other format',
  ),
  SwanOnlyCheck(
    _swan_path('Notrump.one_notrump_opening.two_clubs.other'),
    'Bridgodex records the 1NT-2!c "Other" field as text'
    ' (1_no_trump.2c_other) and SWAN as a checkbox',
  ),
  SwanOnlyCheck(
    _swan_path('Notrump.one_notrump_opening.range.same_response_no'),
    "Bridgodex has only the 'same responses: yes' checkbox",
  ),
  # BridgeWinners writes this checkbox as a string, so it enters the skeleton as
  # one.
  SwanOnlyText(
    _swan_path('Overcalls.Jump_overcall.conventional'),
    "BridgeWinners' export writes the Jump Overcalls 'Conv' checkbox as empty"
    ' whether or not it is ticked, and its import ignores it, so content here'
    ' means BridgeWinners changed its exporter',
  ),
  SwanOnlyText(
    _swan_path('Carding.smith.smith_expl'),
    'Bridgodex has no Smith Echo description blank',
  ),
  SwanOnlyCheck(
    _swan_path('Two_level.two_hearts.conventional'),
    "the ACBL card (and Bridgodex) give 2!h a '2 Suits' checkbox where"
    " BridgeWinners has 'Conventional'",
  ),
  SwanOnlyCheck(
    _swan_path('Two_level.two_spades.conventional'),
    "the ACBL card (and Bridgodex) give 2!s a '2 Suits' checkbox where"
    " BridgeWinners has 'Conventional'",
  ),
  SwanOnlyCircle(
    _swan_path('Leads_vs_notrump.interior_seq.ace_ten_nine'),
    ('ace', 'ten', 'nine', 'low'),
    'BridgeWinners prints an AT9x interior sequence; the ACBL card (and'
    ' Bridgodex) print KT9x instead',
  ),
)

# Bridgodex keys with no SWAN counterpart, and why; conversion warns when one
# carries content.
BRIDGODEX_ONLY: dict[BridgodexKey, str] = {
  _bridgodex_key('names.names'): (
    "BridgeWinners' import ignores player names; set them on BridgeWinners"
    ' after importing'
  ),
  _bridgodex_key('overcalls.conv'): (
    "BridgeWinners' import ignores the Jump Overcalls 'Conv' checkbox; tick it"
    ' on BridgeWinners after importing'
  ),
  _bridgodex_key('overview.forcing_other'): (
    'SWAN records the Forcing Openings "Other" field as a checkbox, with'
    ' nowhere to put text'
  ),
  _bridgodex_key('other.vs_very_strong'): (
    "BridgeWinners' export drops the (Very)Str Open blank's content; the SWAN"
    " keys named for that blank carry the section's two free lines instead"
  ),
  _bridgodex_key('1_no_trump.2c_other'): (
    'SWAN records the 1NT-2!c "Other" field as a checkbox, with nowhere to put'
    ' text'
  ),
  _bridgodex_key('two_level.2h_2_suits'): (
    'SWAN has no 2-suits checkbox for 2!h'
  ),
  _bridgodex_key('two_level.2s_2_suits'): (
    'SWAN has no 2-suits checkbox for 2!s'
  ),
  _bridgodex_key('leads_vs_suits.honor_leads_T9x'): (
    'BridgeWinners prints no T9x honor-lead holding'
  ),
  _bridgodex_key('leads_vs_nt.honor_interior_seq_KT9x'): (
    'BridgeWinners prints AT9x where the ACBL card prints KT9x'
  ),
}

# Top-level SWAN entries that are format metadata, not card content.
IGNORED_SWAN_PATHS: frozenset[tuple[str, ...]] = frozenset(
  {_swan_path('New_Format')}
)
