-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Bold the major-suit placeholder in shorthand: the `M` ending a compound
-- such as `OM`, `2M`, `W2M`, `Q3M`, `4cM`, or `4+OM` is set strong, so the
-- placeholder pops out of the surrounding capitals at a glance. Compounds
-- are written apart — `4cM & 5+m` — so each one ends its own word, and an
-- `M` qualifies when it ends a word that two checks accept:
--
-- - just before it: a digit, `+`, the card-count `c`, the start of the
--   word, or an `O` directly after one of those (or at the word start);
-- - anything earlier in the word: digits, capitals, `+`, and `c` only.
--
-- Ordinary words stay plain — `Major` and `IMP` do not end in `M`, `BAM`
-- fails the just-before check — as does the lowercase minor placeholder `m`.
--
-- The plain-text rendering keeps shorthand exactly as typed, so the filter
-- leaves that format untouched.

-- A maximal word run — the unit the placeholder checks judge — with its
-- bounds.
local word_run = '()([0-9A-Za-z+]+)()'

-- Whether everything before a word's closing `M` marks it as the major
-- placeholder: the two checks in the header comment.
local function is_placeholder_prefix(prefix)
  if not prefix:match('^[0-9A-Z+c]*$') then
    return false
  end
  if prefix:match('O$') then
    prefix = prefix:sub(1, -2)
  end
  return prefix == '' or prefix:match('[0-9+c]$') ~= nil
end

function Str(element)
  if FORMAT == 'plain' then
    return nil
  end
  local text = element.text
  -- Most strings carry no capital `M` at all; skip them outright.
  if not text:find('M', 1, true) then
    return nil
  end
  local inlines = pandoc.Inlines({})
  local position = 1
  local did_bold = false
  while true do
    local start, word, finish = text:match(word_run, position)
    if not start then
      break
    end
    if start > position then
      inlines:insert(pandoc.Str(text:sub(position, start - 1)))
    end
    -- Emit the word, splitting off a closing placeholder `M` to bold it.
    if word:sub(-1) == 'M' and is_placeholder_prefix(word:sub(1, -2)) then
      did_bold = true
      if #word > 1 then
        inlines:insert(pandoc.Str(word:sub(1, -2)))
      end
      inlines:insert(pandoc.Strong({ pandoc.Str('M') }))
    else
      inlines:insert(pandoc.Str(word))
    end
    position = finish
  end
  if not did_bold then
    return nil
  end
  if position <= #text then
    inlines:insert(pandoc.Str(text:sub(position)))
  end
  return inlines
end
