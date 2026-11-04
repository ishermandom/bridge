-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Set each aside apart from the bids around it. An aside is a callout that
-- comments on a bid: a list item written wholly in italic and nested under the
-- bid it explains, such as `- _Note: always 3S, whichever M they bid_`. A list
-- marker displays its line as a round of the auction (spec.md #appearance), and
-- an aside is not itself a bid, so it must not carry a marker. The filter moves
-- each aside out of its list and into the item it annotates, as a div classed
-- `aside`, so the aside reads under that item's own text.
--
-- An aside must stand alone under the item it annotates. When it shares its
-- list with other items, or is nested under no item at all, nothing settles
-- which item it annotates or where it would sit, so the filter fails the render
-- rather than guess.

-- Whether a list item is an aside: one paragraph, italic from its first word to
-- its last. An item that merely opens on an italic term stays an ordinary item.
local function is_aside(item)
  if #item ~= 1 then
    return false
  end
  local block = item[1]
  local is_paragraph = block.t == 'Plain' or block.t == 'Para'
  return is_paragraph
    and #block.content == 1
    and block.content[1].t == 'Emph'
end

-- Fail the render over a misplaced aside, quoting its opening so the author can
-- find it. `problem` finishes the sentence "but this one …".
local function reject_aside(item, problem)
  error(string.format(
    'an aside must stand alone under the item it annotates, but this one %s: '
      .. '"%s"',
    problem, pandoc.utils.stringify(item):sub(1, 80)))
end

-- When `block` is a list holding an aside, return that aside; otherwise return
-- nil. An aside that shares its list with other items fails the render.
local function nested_aside(block)
  if block.t ~= 'BulletList' then
    return nil
  end
  local aside = block.content:find_if(is_aside)
  if aside and #block.content > 1 then
    reject_aside(aside, 'shares its list with other items')
  end
  return aside
end

-- Move each aside nested under one of this list's items into that item.
local function absorb_asides(list)
  for _, item in ipairs(list.content) do
    for index, block in ipairs(item) do
      local aside = nested_aside(block)
      if aside then
        item[index] = pandoc.Div(aside, { class = 'aside' })
      end
    end
  end
  return list
end

-- Fail the render over an aside left in a list after `absorb_asides` has run
-- over the whole document. That pass moves every aside nested under an item,
-- so one left behind is nested under none and annotates nothing.
local function reject_stray_aside(list)
  local aside = list.content:find_if(is_aside)
  if aside then
    reject_aside(aside, 'is nested under no item')
  end
end

-- Two passes, so the check for strays sees the document only after
-- `absorb_asides` has finished with all of it.
return {
  { BulletList = absorb_asides },
  { BulletList = reject_stray_aside },
}
