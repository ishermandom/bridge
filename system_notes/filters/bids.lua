-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Suit symbols and bid strains. Two ways the source asks for them:
--
-- - A bid written plainly — `4S`, `2NT`, `3C` — is detected when its level
--   1–7 and strain stand together as a word of their own, and its strain
--   is rendered: a suit becomes its symbol, and notrump's `NT` stays `NT`.
--   Notrump typed any way but `NT` — `2N`, `2n`, `2nt` — is an error, so
--   the old notation and its lowercase slips cannot pass as undetected
--   prose.
-- - `!S !H !D !C` (either case) asks for a suit symbol anywhere else, for a
--   suit outside a bid: `a !H lead`.
--
-- Every strain becomes a span classed `strain` — a suit also gets `suit` and
-- its name — for the stylesheet's suit face and colors; a detected bid is
-- wrapped whole in a span classed `bid` so its level and strain never part
-- at a line break.
--
-- The plain-text rendering is for pasting into email, where the suit letters
-- read better than symbols: there, a bid stays exactly as typed and an
-- explicit `!h` becomes its letter, `H`.
--
-- The patterns spell out ASCII ranges instead of `%a` and `%w`: those classes
-- consult the C library's locale tables, which on macOS count the lead byte
-- of an en dash as a letter, and the boundary after `1NT` in `1NT–2S` would
-- fail.

local suits = {
  S = { symbol = '♠', class = 'spade' },
  H = { symbol = '♥', class = 'heart' },
  D = { symbol = '♦', class = 'diamond' },
  C = { symbol = '♣', class = 'club' },
}

-- A level and any notrump spelling, for the error check below: only `NT`
-- itself is legal.
local notrump_spelling = '()%f[A-Za-z0-9][1-7]([Nn][Tt]?)%f[^A-Za-z]'

-- Error on notrump typed any way but `NT`: a bare `N` (the old notation) or
-- a lowercase slip such as `2nt`. The notation is uppercase, so an
-- uppercase spelling always errors — `1N-2S` is old notation, not prose —
-- while a lowercase one next to a joining `-` or `+` marks non-notation
-- text (a URL path, algebra like `2n+1`) and is left alone.
local function check_notrump(text)
  local position = 1
  while true do
    local start, strain = text:match(notrump_spelling, position)
    if not start then
      return
    end
    local finish = start + 1 + #strain
    local before = text:sub(start - 1, start - 1)
    local after = text:sub(finish, finish)
    local is_lowercase_slip = strain ~= strain:upper()
    local has_joining_neighbor = before == '-'
      or before == '+'
      or after == '-'
      or after == '+'
    if
      strain ~= 'NT'
      and not (is_lowercase_slip and has_joining_neighbor)
    then
      error(
        'notrump must always be spelled NT, never '
          .. strain .. ': "' .. text .. '"')
    end
    position = finish
  end
end

local function strain_span(strain)
  local suit = suits[strain:upper()]
  if suit then
    return pandoc.Span(
      { pandoc.Str(suit.symbol) }, { class = 'strain suit ' .. suit.class })
  end
  return pandoc.Span({ pandoc.Str('NT') }, { class = 'strain notrump' })
end

-- The notation as a grammar: each rule names one piece, `/` tries the
-- alternatives in order, and `!` means "not followed by". The grammar reads
-- the text a whole word at a time, so a bid can only begin where a word
-- begins: `15S` and `5S4H` stay prose.
local notation_grammar = [[
  pieces         <- {| (notation / prose)* |}
  notation       <- bid / explicit_suit

  -- A level and a strain forming a whole word: `1ST` is not `1S`.
  bid            <- ({level} {strain} !word_character) -> render_bid
  level          <- [1-7]
  strain         <- [SHDC] / 'NT'

  -- `!` and a suit letter, not followed by another letter: `!Stayman` is
  -- prose.
  explicit_suit  <- ('!' {[SHDCshdc]} !letter) -> render_suit

  prose          <- { (!notation (word / !word_character .))+ } -> render_prose
  word           <- word_character+
  word_character <- [A-Za-z0-9]
  letter         <- [A-Za-z]
]]

-- What each piece of notation becomes, for the styled renderings.
local styled_rendering = {
  render_bid = function(level, strain)
    return pandoc.Span(
      { pandoc.Str(level), strain_span(strain) }, { class = 'bid' })
  end,
  render_suit = strain_span,
  render_prose = pandoc.Str,
}

-- What each piece of notation becomes in plain text: a bid stays as typed,
-- and an explicit suit drops its `!`.
local plain_text_rendering = {
  render_bid = function(level, strain)
    return pandoc.Str(level .. strain)
  end,
  render_suit = function(letter)
    return pandoc.Str(letter:upper())
  end,
  render_prose = pandoc.Str,
}

local notation_parser = re.compile(
  notation_grammar,
  FORMAT == 'plain' and plain_text_rendering or styled_rendering)

local function render_bids_and_suits(element)
  check_notrump(element.text)
  local inlines = pandoc.Inlines(notation_parser:match(element.text))
  -- Text without notation comes back as one piece, equal to the original.
  if #inlines == 1 and inlines[1] == element then
    return nil
  end
  return inlines
end

return { Str = render_bids_and_suits }
