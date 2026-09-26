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

-- `!` and a suit letter, not followed by another letter (`!Stayman` is prose).
local explicit_suit = '!([SHDCshdc])%f[^A-Za-z]'
-- A level and a suit letter as a word: no word character before the level
-- (`15S` is not a bid), no letter or digit after the strain (`1ST` is not
-- `1S`, and run-together shape shorthand like `5S4H` stays prose whole
-- rather than half-styling).
local suit_bid = '%f[A-Za-z0-9]([1-7])([SHDC])%f[^A-Za-z0-9]'
-- A level and `NT` as a word.
local notrump_bid = '%f[A-Za-z0-9]([1-7])(NT)%f[^A-Za-z0-9]'
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

-- The earliest bid or explicit suit at or after `position`, as
-- (start, finish, level or nil, strain), or nil when there is none. A bid
-- and an explicit suit can never start at the same place: one opens with a
-- level digit, the other with `!`.
local function next_match(text, position)
  local best_start, best_finish, best_level, best_strain
  for _, bid in ipairs({ suit_bid, notrump_bid }) do
    local start, finish, level, strain = text:find(bid, position)
    if start and (not best_start or start < best_start) then
      best_start, best_finish, best_level, best_strain =
        start, finish, level, strain
    end
  end
  local start, finish, letter = text:find(explicit_suit, position)
  if start and (not best_start or start < best_start) then
    return start, finish, nil, letter
  end
  return best_start, best_finish, best_level, best_strain
end

local function render_bids_and_suits(element)
  local text = element.text
  check_notrump(text)
  if FORMAT == 'plain' then
    -- Bids stay as typed; only the `!` of explicit shorthand comes off.
    local replaced = text:gsub(explicit_suit, function(letter)
      return letter:upper()
    end)
    if replaced == text then
      return nil
    end
    return pandoc.Str(replaced)
  end
  if not next_match(text, 1) then
    return nil
  end

  local inlines = pandoc.Inlines({})
  local position = 1
  while true do
    local start, finish, level, strain = next_match(text, position)
    if not start then
      break
    end
    if start > position then
      inlines:insert(pandoc.Str(text:sub(position, start - 1)))
    end
    if level then
      inlines:insert(pandoc.Span(
        { pandoc.Str(level), strain_span(strain) }, { class = 'bid' }))
    else
      inlines:insert(strain_span(strain))
    end
    position = finish + 1
  end
  if position <= #text then
    inlines:insert(pandoc.Str(text:sub(position)))
  end
  return inlines
end

return { Str = render_bids_and_suits }
