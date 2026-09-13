# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""The vocabulary: what each card JSON key means on the ACBL card.

Each setting maps to its target on the card: a text field to write in, a
checkbox to mark, or a lead-chart card to circle. This table is the single place
a key's meaning is recorded; it was reverse-engineered by matching a full
Bridgodex export against the card's own form-field names (see `spec.md`).

Unknown input is a hard error: content the card was asked to show must never go
silently missing. Keys the Bridgodex export format carries but no card layout
can print are listed in `UNRENDERED_KEYS`; a nonempty value in one is rejected
so the player moves the content to a field that prints, rather than losing it
silently.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from bridgodex_key import BridgodexKey

from renderer.lead_charts import CHART_BOXES, CharBox


@dataclass(frozen=True)
class TextEntry:
  """The value is text drawn into a form text field, shrink-to-fit."""

  field_name: str


@dataclass(frozen=True)
class CheckMark:
  """The value marks a checkbox field with an X.

  Bridgodex exports a checked box as the string 'on' and leaves unchecked boxes
  out entirely, so 'on' is the only value accepted.
  """

  field_name: str


@dataclass(frozen=True)
class CircleLeadCard:
  """The value picks which printed card of a lead holding gets circled.

  The value is the card's 1-based position from the left; `boxes` holds the
  boxes of the holding's printed characters, left to right (see `lead_charts`).
  """

  boxes: tuple[CharBox, ...]


# Where a key's value lands on the card, and how it draws there.
type Target = TextEntry | CheckMark | CircleLeadCard


def _section(
  name: str, entries: Mapping[str, Target]
) -> dict[BridgodexKey, Target]:
  """Qualify one section's key -> target entries with the section name."""
  return {BridgodexKey(name, key): target for key, target in entries.items()}


VOCABULARY: Mapping[BridgodexKey, Target] = {
  **_section(
    'names',
    {
      'names': TextEntry('Name.t.1'),
    },
  ),
  **_section(
    'overview',
    {
      'general_approach': TextEntry('OV.t.1'),
      'min_exp_hcp_bal_opening': TextEntry('OV.t.2'),
      'min_exp_hcp_bal_responding': TextEntry('OV.t.3'),
      'forcing_1c': CheckMark('OV.c.4'),
      'forcing_2c': CheckMark('OV.c.5'),
      'forcing_other': TextEntry('OV.t.6'),
      '1nt_open_strong': CheckMark('OV.c.7'),
      '1nt_open_weak': CheckMark('OV.c.8'),
      '1nt_open_variable': CheckMark('OV.c.9'),
      'bids_that_may_require_prep': TextEntry('OV.t.10'),
      'more': TextEntry('OV.t.11'),
    },
  ),
  **_section(
    'other',
    {
      'jump_shift_resp': TextEntry('O.t.1'),
      'vs_very_strong': TextEntry('O.t.2'),
      'nmf': CheckMark('O.c.3'),
      '2_way_nmf': CheckMark('O.c.4'),
      'xyz': CheckMark('O.c.5'),
      'fsf_1rnd': CheckMark('O.c.6'),
      'fsf_gf': CheckMark('O.c.7'),
      'more1': TextEntry('O.t.8'),
      'more2': TextEntry('O.t.9'),
    },
  ),
  **_section(
    'majors',
    {
      'min_len_1st_2nd_4': CheckMark('1H1S.c.1'),
      'min_len_1st_2nd_5': CheckMark('1H1S.c.2'),
      'min_len_3rd_4th_4': CheckMark('1H1S.c.3'),
      'min_len_3rd_4th_5': CheckMark('1H1S.c.4'),
      '1nt_forcing': CheckMark('1H1S.c.5'),
      '1nt_semi_forcing': CheckMark('1H1S.c.6'),
      'bypass_1_spade': CheckMark('1H1S.c.7'),
      'art_raises_2nt': CheckMark('1H1S.c.8'),
      'art_raises_3nt': CheckMark('1H1S.c.9'),
      'art_raises_splinter': CheckMark('1H1S.c.10'),
      'art_raises_other': TextEntry('1H1S.t.11'),
      'drury_2c': CheckMark('1H1S.c.12'),
      'drury_2d': CheckMark('1H1S.c.13'),
      'drury_in_comp': CheckMark('1H1S.c.14'),
      'drury_other': TextEntry('1H1S.t.15'),
      'other': TextEntry('1H1S.t.16'),
      'more': TextEntry('1H1S.t.16b'),
      'jump_raise_weak': CheckMark('1H1S.c.17'),
      'jump_raise_mixed': CheckMark('1H1S.c.18'),
      'jump_raise_inv': CheckMark('1H1S.c.19'),
      'jump_raise_overcall_weak': CheckMark('1H1S.c.20'),
      'jump_raise_overcall_mixed': CheckMark('1H1S.c.21'),
      'jump_raise_overcall_inv': CheckMark('1H1S.c.22'),
    },
  ),
  **_section(
    'minors',
    {
      '1c_min_len_5': CheckMark('1C.c.1'),
      '1c_min_len_4': CheckMark('1C.c.2'),
      '1c_min_len_3': CheckMark('1C.c.3'),
      '1c_min_len_nf_2': CheckMark('1C.c.4'),
      '1c_min_len_nf_2_4432': CheckMark('1C.c.5'),
      '1c_min_len_nf_1': CheckMark('1C.c.6'),
      '1c_min_len_nf_0': CheckMark('1C.c.7'),
      '1c_min_len_art_f': CheckMark('1C.c.8'),
      '1c_response': TextEntry('1C.t.9'),
      '1c_trans_resp': CheckMark('1C.c.10'),
      '1c_more': TextEntry('1C.t.11'),
      '1c_1d': TextEntry('1C.t.12'),
      '1c_1d_bypass_5': CheckMark('1C.c.13'),
      '1c_1nt_min': TextEntry('1C.t.14'),
      '1c_1nt_max': TextEntry('1C.t.15'),
      '1c_2nt_min': TextEntry('1C.t.16'),
      '1c_2nt_max': TextEntry('1C.t.17'),
      '1c_single_raise_nf': CheckMark('1C.c.18'),
      '1c_single_raise_inv': CheckMark('1C.c.19'),
      '1c_single_raise_gf': CheckMark('1C.c.20'),
      '1c_jump_raise_weak': CheckMark('1C.c.21'),
      '1c_jump_raise_mixed': CheckMark('1C.c.22'),
      '1c_jump_raise_inv': CheckMark('1C.c.23'),
      '1c_jump_raise_overcall_weak': CheckMark('1C.c.24'),
      '1c_jump_raise_overcall_mixed': CheckMark('1C.c.25'),
      '1c_jump_raise_overcall_inv': CheckMark('1C.c.26'),
      '1d_min_len_5': CheckMark('1D.c.1'),
      '1d_min_len_4': CheckMark('1D.c.2'),
      '1d_min_len_3': CheckMark('1D.c.3'),
      '1d_min_len_unbal': CheckMark('1D.c.4'),
      '1d_min_len_nf_2': CheckMark('1D.c.5'),
      '1d_min_len_nf_1': CheckMark('1D.c.6'),
      '1d_min_len_nf_0': CheckMark('1D.c.7'),
      '1d_min_len_art_f': CheckMark('1D.c.8'),
      '1d_response': TextEntry('1D.t.9'),
      '1d_same_as_1c': CheckMark('1D.c.10'),
      '1d_more': TextEntry('1D.t.11'),
      '1d_1nt_min': TextEntry('1D.t.12'),
      '1d_1nt_max': TextEntry('1D.t.13'),
      '1d_2nt_min': TextEntry('1D.t.14'),
      '1d_2nt_max': TextEntry('1D.t.15'),
      '1d_single_raise_nf': CheckMark('1D.c.16'),
      '1d_single_raise_inv': CheckMark('1D.c.17'),
      '1d_single_raise_gf': CheckMark('1D.c.18'),
      '1d_jump_raise_weak': CheckMark('1D.c.19'),
      '1d_jump_raise_mixed': CheckMark('1D.c.20'),
      '1d_jump_raise_inv': CheckMark('1D.c.21'),
      '1d_jump_raise_overcall_weak': CheckMark('1D.c.22'),
      '1d_jump_raise_overcall_mixed': CheckMark('1D.c.23'),
      '1d_jump_raise_overcall_inv': CheckMark('1D.c.24'),
    },
  ),
  **_section(
    '1_no_trump',
    {
      'a_range_min': TextEntry('1NT.t.1'),
      'a_range_max': TextEntry('1NT.t.2'),
      'a_range_seat_vul': TextEntry('1NT.t.3'),
      '5_card_major': CheckMark('1NT.c.4'),
      'sys_on_vs': TextEntry('1NT.t.5'),
      '2c_stayman': CheckMark('1NT.c.6'),
      '2c_puppet': CheckMark('1NT.c.7'),
      '2d_nat': CheckMark('1NT.c.9'),
      '2d_tfr': CheckMark('1NT.c.10'),
      '2d_other': TextEntry('1NT.t.11'),
      '2h_nat': CheckMark('1NT.c.12'),
      '2h_tfr': CheckMark('1NT.c.13'),
      '2h_other': TextEntry('1NT.t.14'),
      '2s_nat': CheckMark('1NT.c.15'),
      '2s_tfr': CheckMark('1NT.c.16'),
      '2s_other': TextEntry('1NT.t.17'),
      '2nt_nat': CheckMark('1NT.c.18'),
      '2nt_tfr': CheckMark('1NT.c.19'),
      '2nt_other': TextEntry('1NT.t.20'),
      'smolen': CheckMark('1NT.c.21'),
      'tfr_4c': CheckMark('1NT.c.22'),
      'tfr_4d': CheckMark('1NT.c.23'),
      'tfr_4h': CheckMark('1NT.c.24'),
      'dbl_neg': CheckMark('1NT.c.25'),
      'dbl_neg_desc': TextEntry('1NT.t.26'),
      'dbl_pen': CheckMark('1NT.c.27'),
      'b_range_min': TextEntry('1NT.t.28'),
      'b_range_max': TextEntry('1NT.t.29'),
      'b_range_same_resp': CheckMark('1NT.c.30'),
      '3c': TextEntry('1NT.t.32'),
      '3d': TextEntry('1NT.t.33'),
      '3h': TextEntry('1NT.t.34'),
      '3s': TextEntry('1NT.t.35'),
      'other': TextEntry('1NT.t.36'),
      'more': TextEntry('1NT.t.37'),
      'dbl_other': TextEntry('1NT.t.38'),
      'lebensohl': CheckMark('1NT.c.39'),
      'lebensohl_desc': TextEntry('1NT.t.40'),
    },
  ),
  **_section(
    '2_no_trump',
    {
      'range_min': TextEntry('2NT.t.1'),
      'range_max': TextEntry('2NT.t.2'),
      'puppet': CheckMark('2NT.c.3'),
      '3s': CheckMark('2NT.c.4'),
      '3s_desc': TextEntry('2NT.t.5'),
      'conv': CheckMark('2NT.c.6'),
      'conv_desc': TextEntry('2NT.t.7'),
      'tfr_3lvl': CheckMark('2NT.c.8'),
      'tfr_4lvl': CheckMark('2NT.c.9'),
      'neg_dbl': CheckMark('2NT.c.10'),
      'other': TextEntry('2NT.t.11'),
    },
  ),
  **_section(
    '3_no_trump',
    {
      'range_min': TextEntry('3NT.t.1'),
      'range_max': TextEntry('3NT.t.2'),
      'one_suit': CheckMark('3NT.c.3'),
      'one_suit_desc': TextEntry('3NT.t.4'),
    },
  ),
  **_section(
    'two_level',
    {
      '2c_min': TextEntry('2C.t.1'),
      '2c_max': TextEntry('2C.t.2'),
      '2c_range_desc': TextEntry('2C.t.3a'),
      '2c_2d_neg': CheckMark('2C.c.3b'),
      '2c_2d_waiting': CheckMark('2C.c.4'),
      '2c_steps': CheckMark('2C.c.5'),
      '2c_steps_desc': TextEntry('2C.t.6'),
      '2c_2h_neg': CheckMark('2C.c.7'),
      '2c_very_str': CheckMark('2C.c.8'),
      '2c_str': CheckMark('2C.c.9'),
      '2c_nat': CheckMark('2C.c.10'),
      '2c_conv': CheckMark('2C.c.11'),
      '2c_conv_desc': TextEntry('2C.t.12'),
      '2c_other': TextEntry('2C.t.13'),
      '2d_min': TextEntry('2D.t.1'),
      '2d_max': TextEntry('2D.t.2'),
      '2d_desc': TextEntry('2D.t.3'),
      '2d_nsnf': CheckMark('2D.c.4'),
      '2d_weak': CheckMark('2D.c.5'),
      '2d_int': CheckMark('2D.c.6'),
      '2d_str': CheckMark('2D.c.7'),
      '2d_conv': CheckMark('2D.c.8'),
      '2d_rebids_2nt': TextEntry('2D.t.9'),
      '2d_other': TextEntry('2D.t.10'),
      '2h_min': TextEntry('2H.t.1'),
      '2h_max': TextEntry('2H.t.2'),
      '2h_desc': TextEntry('2H.t.3'),
      '2h_nsnf': CheckMark('2H.c.4'),
      '2h_weak': CheckMark('2H.c.5'),
      '2h_int': CheckMark('2H.c.6'),
      '2h_str': CheckMark('2H.c.7'),
      '2h_2_suits': CheckMark('2H.c.8'),
      '2h_rebids_2nt': TextEntry('2H.t.9'),
      '2h_other': TextEntry('2H.t.10'),
      '2s_min': TextEntry('2S.t.1'),
      # The official PDF misnames the 2S range's "to" blank as '21.t.2'.
      '2s_max': TextEntry('21.t.2'),
      '2s_desc': TextEntry('2S.t.3'),
      '2s_nsnf': CheckMark('2S.c.4'),
      '2s_weak': CheckMark('2S.c.5'),
      '2s_int': CheckMark('2S.c.6'),
      '2s_str': CheckMark('2S.c.7'),
      '2s_2_suits': CheckMark('2S.c.8'),
      '2s_rebids_2nt': TextEntry('2S.t.9'),
      '2s_other': TextEntry('2S.t.10'),
    },
  ),
  **_section(
    'doubles',
    {
      'negative': CheckMark('D.c.1'),
      'negative_thru': TextEntry('D.t.2'),
      'penalty': CheckMark('D.c.3'),
      'responsive': CheckMark('D.c.4'),
      'responsive_thru': TextEntry('D.t.5'),
      'maximal': CheckMark('D.c.6'),
      'support': CheckMark('D.c.7'),
      'support_thru': TextEntry('D.t.8'),
      'support_rdbl': CheckMark('D.c.9'),
      'to_style': TextEntry('D.t.10'),
      'other': TextEntry('D.t.11'),
    },
  ),
  **_section(
    'nt_overcalls',
    {
      'direct_1nt_min': TextEntry('NTO.t.1'),
      'direct_1nt_max': TextEntry('NTO.t.2'),
      'direct_systems_on': CheckMark('NTO.c.3'),
      'balance_1nt_min': TextEntry('NTO.t.4'),
      'balance_1nt_max': TextEntry('NTO.t.5'),
      'balance_systems_on': CheckMark('NTO.c.6'),
      'conv': CheckMark('NTO.c.7'),
      'conv_desc': TextEntry('NTO.t.8'),
      'jump_2nt_2_lowest_unbid': CheckMark('NTO.c.9'),
      'other': TextEntry('NTO.t.10'),
    },
  ),
  **_section(
    'overcalls',
    {
      '1_lvl_min': TextEntry('OC.t.1'),
      '1_lvl_max': TextEntry('OC.t.2'),
      '1_lvl_4cards': CheckMark('OC.c.3'),
      '2_lvl_min': TextEntry('OC.t.4'),
      '2_lvl_max': TextEntry('OC.t.5'),
      'jump_weak': CheckMark('OC.c.6'),
      'jump_int': CheckMark('OC.c.7'),
      'jump_strong': CheckMark('OC.c.8'),
      'conv': CheckMark('OC.c.9'),
      'conv_desc': TextEntry('OC.t.10'),
      'new_suit_forcing': CheckMark('OC.c.11'),
      'new_suit_nf_const': CheckMark('OC.c.12'),
      'new_suit_nf': CheckMark('OC.c.13'),
      'new_suit_tfr': CheckMark('OC.c.14'),
      'jump_raise_wk': CheckMark('OC.c.15'),
      'jump_raise_mixed': CheckMark('OC.c.16'),
      'jump_raise_inv': CheckMark('OC.c.17'),
      'cuebids': TextEntry('OC.t.18'),
      'cue_support': CheckMark('OC.c.19'),
      'other': TextEntry('OC.t.20'),
    },
  ),
  **_section(
    'direct_cuebids',
    {
      'art_michaels': CheckMark('DC.c.1'),
      'quasi_michaels': CheckMark('DC.c.2'),
      'nat_minors_michaels': CheckMark('DC.c.3'),
      'nat_majors_michaels': CheckMark('DC.c.4'),
      'art_natural': CheckMark('DC.c.5'),
      'quasi_natural': CheckMark('DC.c.6'),
      'nat_minors_natural': CheckMark('DC.c.7'),
      'nat_majors_natural': CheckMark('DC.c.8'),
      'art_other': CheckMark('DC.c.9'),
      'quasi_other': CheckMark('DC.c.10'),
      'nat_minors_other': CheckMark('DC.c.11'),
      'nat_majors_other': CheckMark('DC.c.12'),
      'describe': TextEntry('DC.t.13'),
    },
  ),
  **_section(
    'vs_1nt_opening',
    {
      'vs_a': TextEntry('V1NT.t.1'),
      'vs_b': TextEntry('V1NT.t.2'),
      'vs_a_dbl': TextEntry('V1NT.t.3'),
      'vs_b_dbl': TextEntry('V1NT.t.4'),
      'vs_a_2c': TextEntry('V1NT.t.5'),
      'vs_b_2c': TextEntry('V1NT.t.6'),
      'vs_a_2d': TextEntry('V1NT.t.7'),
      'vs_b_2d': TextEntry('V1NT.t.8'),
      'vs_a_2h': TextEntry('V1NT.t.9'),
      'vs_b_2h': TextEntry('V1NT.t.10'),
      'vs_a_2s': TextEntry('V1NT.t.11'),
      'vs_b_2s': TextEntry('V1NT.t.12'),
      'vs_a_2nt': TextEntry('V1NT.t.13'),
      'vs_b_2nt': TextEntry('V1NT.t.14'),
      'other': TextEntry('V1NT.t.15'),
    },
  ),
  **_section(
    'vs_to_double',
    {
      'new_suit_forcing_2_lvl': CheckMark('VTD.c.1'),
      'new_suit_forcing_transfer': CheckMark('VTD.c.2'),
      'new_suit_forcing_transfer_desc': TextEntry('VTD.t.3'),
      'jump_shift_weak': CheckMark('VTD.c.4'),
      'jump_shift_inv': CheckMark('VTD.c.5'),
      'jump_shift_f': CheckMark('VTD.c.6'),
      'jump_shift_fit': CheckMark('VTD.c.7'),
      'redouble_10_plus': CheckMark('VTD.c.8'),
      'redouble_conv': CheckMark('VTD.c.9'),
      'redouble_conv_desc': TextEntry('VTD.t.10'),
      '2nt_over_minors_nat': CheckMark('VTD.c.11'),
      '2nt_over_minors_raise': CheckMark('VTD.c.12'),
      '2nt_over_minors_min': TextEntry('VTD.t.13'),
      '2nt_over_minors_max': TextEntry('VTD.t.14'),
      '2nt_over_majors_nat': CheckMark('VTD.c.15'),
      '2nt_over_majors_raise': CheckMark('VTD.c.16'),
      '2nt_over_majors_min': TextEntry('VTD.t.17'),
      '2nt_over_majors_max': TextEntry('VTD.t.18'),
      'other': TextEntry('VTD.t.19'),
    },
  ),
  **_section(
    'vs_preempts',
    {
      '2nt_overcall': TextEntry('VP.t.1'),
      'to_dbl_thru': TextEntry('VP.t.2'),
      'to_dbl_penalty': CheckMark('VP.c.3'),
      '2nt_lebensohl_resp': CheckMark('VP.c.4'),
      '2nt_lebensohl_resp_desc': TextEntry('VP.t.4'),
      'cuebid': TextEntry('VP.t.5'),
      'jump_overcalls': TextEntry('VP.t.6'),
      'other': TextEntry('VP.t.7'),
    },
  ),
  **_section(
    'preempts',
    {
      '3_lvl_style': TextEntry('P.t.1'),
      '3_lvl_more': TextEntry('P.t.2'),
      '3_lvl_resp': TextEntry('P.t.3'),
      '4_lvl_style': TextEntry('P.t.4'),
      '4_lvl_resp': TextEntry('P.t.5'),
      '4_lvl_minors_transfer': CheckMark('P.c.6'),
      '4_lvl_other': TextEntry('P.t.7'),
    },
  ),
  **_section(
    'slams',
    {
      'gerber_directly_over_nt': CheckMark('SL.c.1'),
      'gerber_over_nt_seq': CheckMark('SL.c.2'),
      'gerber_over_non_nt_seq': CheckMark('SL.c.3'),
      'gerber_other': TextEntry('SL.t.4'),
      '4nt_blackwood': CheckMark('SL.c.5'),
      '4nt_rkc_0314': CheckMark('SL.c.6'),
      '4nt_rkc_1430': CheckMark('SL.c.7'),
      '4nt_more': TextEntry('SL.t.8'),
      'control_bids': TextEntry('SL.t.9'),
      'vs_interference': TextEntry('SL.t.10'),
      'other': TextEntry('SL.t.11'),
    },
  ),
  **_section(
    'carding',
    {
      'suits_std_att': CheckMark('C.c.1'),
      'nt_std_att': CheckMark('C.c.2'),
      'suits_std_count': CheckMark('C.c.3'),
      'nt_std_count': CheckMark('C.c.4'),
      'suits_ud_att': CheckMark('C.c.5'),
      'nt_ud_att': CheckMark('C.c.6'),
      'suits_ud_count': CheckMark('C.c.7'),
      'nt_ud_count': CheckMark('C.c.8'),
      'exceptions': TextEntry('C.t.9'),
      'other': TextEntry('C.t.10'),
      'smith_echo_suits': CheckMark('C.c.11'),
      'smith_echo_nt': CheckMark('C.c.12'),
      'smith_echo_reverse': CheckMark('C.c.13'),
      'trump_signals': TextEntry('C.t.15'),
    },
  ),
  **_section(
    'signals',
    {
      'declarer_lead_att': CheckMark('SI.c.2'),
      'partner_lead_att': CheckMark('SI.c.3'),
      'declarer_lead_count': CheckMark('SI.c.4'),
      'partner_lead_count': CheckMark('SI.c.5'),
      'declarer_lead_pref': CheckMark('SI.c.6'),
      'partner_lead_pref': CheckMark('SI.c.7'),
      'exceptions': TextEntry('SI.t.8'),
      'first_discard_std': CheckMark('SI.c.9'),
      'first_discard_ud': CheckMark('SI.c.10'),
      'lavinthal': CheckMark('SI.c.11'),
      'odd_even': CheckMark('SI.c.12'),
      'other': CheckMark('SI.c.13'),
      'other1': TextEntry('SI.t.14'),
      'other2': TextEntry('SI.t.15'),
    },
  ),
  **_section(
    'leads_vs_suits',
    {
      'length_4th': CheckMark('LS.c.1'),
      'length_3rd_5th': CheckMark('LS.c.2'),
      'length_3rd_low': CheckMark('LS.c.3'),
      'attitude': CheckMark('LS.c.4'),
      'small_from_xx': CheckMark('LS.c.5'),
      'after_1st_trick': TextEntry('LS.t.6'),
      'honor_leads_akx_varies': CheckMark('LS.c.7'),
      'honor_leads_akx_varies_desc': TextEntry('LS.t.8'),
      'exceptions': TextEntry('LS.t.9'),
    },
  ),
  **_section(
    'leads_vs_nt',
    {
      'length_4th': CheckMark('LN.c.1'),
      'length_3rd_5th': CheckMark('LN.c.2'),
      'length_3rd_low': CheckMark('LN.c.3'),
      'attitude': CheckMark('LN.c.4'),
      'second_from_xxxxn': CheckMark('LN.c.5'),
      'after_1st_trick': TextEntry('LN.t.6'),
      'honor_leads_akx_varies': CheckMark('LN.c.7'),
      'honor_leads_akx_varies_desc': TextEntry('LN.t.8'),
      'exceptions': TextEntry('LN.t.9'),
    },
  ),
  # The numeric lead keys, one per measured holding in the lead charts.
  **{key: CircleLeadCard(boxes) for key, boxes in CHART_BOXES.items()},
}


# Keys Bridgodex's editor offers but no rendering ever prints: the 2!c response
# row gives "Other" a checkbox (`1NT.c.8`) with no text blank, yet the editor
# still offers a `2c_other` text field; Bridgodex's own PDF renderer drops that
# field too, so its presence in the editor is a Bridgodex UI bug. Text typed
# there would vanish from every rendering; a nonempty value is rejected so the
# player moves the content to a field that prints. An empty value carries
# nothing to lose and passes.
UNRENDERED_KEYS: frozenset[BridgodexKey] = frozenset(
  {BridgodexKey('1_no_trump', '2c_other')}
)


@dataclass(frozen=True)
class TextPlacement:
  """A validated text value bound for its field."""

  target: TextEntry
  text: str


@dataclass(frozen=True)
class CheckPlacement:
  """A validated check mark bound for its checkbox."""

  target: CheckMark


@dataclass(frozen=True)
class CirclePlacement:
  """A validated lead circle: which printed card of the holding to ring."""

  target: CircleLeadCard
  card_position: int


type Placement = TextPlacement | CheckPlacement | CirclePlacement


def resolve_settings(
  settings: Mapping[str, object],
) -> list[Placement]:
  """Match every settings key to its target, validating values.

  Collects every problem before failing, so one run reports the full list of
  unknown keys and bad values.

  Raises:
    ValueError: if the settings ask for anything the renderer can't deliver.
  """
  placements: list[Placement] = []
  problems: list[str] = []

  for section_name, section in sorted(settings.items()):
    if not isinstance(section, Mapping):
      problems.append(f'section {section_name!r} is not an object')
      continue
    for key, value in sorted(section.items()):
      if not isinstance(key, str):
        problems.append(f'non-string key {key!r} in section {section_name!r}')
        continue
      setting = BridgodexKey(section_name, key)
      placement = _resolve_setting(setting, value, problems)
      if placement is not None:
        placements.append(placement)

  if problems:
    details = '\n  '.join(problems)
    raise ValueError(f'card JSON problems:\n  {details}')
  return placements


def _resolve_setting(
  setting: BridgodexKey,
  value: object,
  problems: list[str],
) -> Placement | None:
  """Resolve one setting against the vocabulary, appending any problem found."""
  if setting in UNRENDERED_KEYS:
    # Only a nonempty value carries content that would be lost.
    if value:
      problems.append(
        f'{setting} = {value!r} never renders: Bridgodex offers the field'
        " but no card layout prints it (not even Bridgodex's own) — move the"
        ' text to a field that prints'
      )
    return None

  target = VOCABULARY.get(setting)
  if target is None:
    problems.append(f'unknown key {setting}')
    return None

  match target:
    case TextEntry():
      if not isinstance(value, str) or not value:
        problems.append(f'{setting} expects non-empty text, got {value!r}')
        return None
      return TextPlacement(target, value)
    case CheckMark():
      if value != 'on':
        problems.append(f"{setting} expects 'on', got {value!r}")
        return None
      return CheckPlacement(target)
    case CircleLeadCard():
      # bool is an int subclass; a JSON true must not pass as position 1.
      position_count = len(target.boxes)
      if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= position_count
      ):
        problems.append(
          f'{setting} expects a card position 1..{position_count},'
          f' got {value!r}'
        )
        return None
      return CirclePlacement(target, value)
