# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Translate between the notations bridge uses for a contract's result.

A result can be written several ways: relative to the contract (overtricks and
undertricks), as a total trick count, or — in the BridgeMate 'American style'
mode this club uses — with makes counted as tricks beyond book. Downstream
analysis needs one notation-independent form to compare on: tricks_taken, the
number of tricks declarer took (0-13). This module translates between those
notations; today it handles the sheet's, with the traveller's to follow when
reconciliation needs it. See spec.md (Notation and normalization).
"""

import re

# Book is the first six tricks, which no contract scores. A contract's level is
# stated above book: a 4-level contract needs ten tricks, book plus four.
_BOOK = 6

# The pattern of a result token: a sign followed by one or more digits.
_RESULT_TOKEN_PATTERN = re.compile(r'([+-])(\d+)')


def tricks_taken_from_sheet_result(result: str, contract_level: int) -> int:
  """Return the tricks declarer took, from a sheet result token.

  The sheet's notation — the BridgeMate 'American style' result-entry mode the
  club uses — writes a make as '+N', N tricks beyond book (six), so '4S +6' is
  twelve tricks; and a set contract as '-N', N tricks short of the contract, so
  '5H -2' on an eleven-trick contract is nine tricks.

  This function only translates notation. It does not judge whether the level or
  the resulting trick count is a legal bridge value — that is the caller's
  responsibility. It raises only when the token cannot be parsed at all.

  Args:
    result: the result token as written, e.g. '+6' or '-2'. A leading minus may
      be an ASCII hyphen or a Unicode minus sign; surrounding space is ignored.
    contract_level: the contract level. Used by the '-N' form, which counts down
      from the contract; unused by '+N'.

  Returns:
    The number of tricks declarer took.

  Raises:
    ValueError: if result is not a well-formed '+N' / '-N' token.
  """
  # Normalize a Unicode minus (U+2212) to ASCII so both transcriptions parse
  # alike — the sheet may be written, or transcribed, with either.
  token = result.strip().replace(chr(0x2212), '-')
  match = _RESULT_TOKEN_PATTERN.fullmatch(token)
  if not match:
    raise ValueError(f'malformed sheet result token: {result!r}')

  sign, count = match.group(1), int(match.group(2))
  if sign == '+':
    # '+N' counts up from book, independent of the contract level.
    return _BOOK + count
  # '-N' counts down from the tricks the contract needed: level plus book.
  return contract_level + _BOOK - count
