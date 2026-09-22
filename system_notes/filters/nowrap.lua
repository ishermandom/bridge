-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Keep short notation tokens on one line. Card-count ranges and shapes
-- (`15–17`, `5-3-3-2`) and slashed shorthand (`P/C`, `NS/JNS`, `m/M`) read as
-- single units, but a line may break after a dash or a slash, and in a narrow
-- column it does. Such a token becomes a span classed `nowrap`; ordinary
-- hyphenated and slashed words (`four-card`, `and/or`) are left breakable, so
-- prose keeps its usual line-break opportunities.

-- A digit, a dash, and another digit: a range or a shape. Lua patterns work
-- on bytes, and an en dash is three of them, so hyphen and en dash need
-- separate patterns rather than one character class.
local digit_hyphen_digit = '[0-9]%-[0-9]'
local digit_en_dash_digit = '[0-9]–[0-9]'
-- A word character or `+` on each side of a slash: a slashed token. It counts
-- as shorthand only when a capital or a digit appears somewhere in it
-- (`P/C`, `m/M`, `5+/4+`); all-lowercase `and/or` is prose.
local word_slash_word = '[A-Za-z0-9+]/[A-Za-z0-9+]'
local capital_or_digit = '[A-Z0-9]'

function Str(element)
  local text = element.text
  local is_slashed_shorthand = text:find(word_slash_word) ~= nil
    and text:find(capital_or_digit) ~= nil
  local is_notation_token = text:find(digit_hyphen_digit) ~= nil
    or text:find(digit_en_dash_digit) ~= nil
    or is_slashed_shorthand
  if not is_notation_token then
    return nil
  end
  return pandoc.Span({ element }, { class = 'nowrap' })
end
