-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Set callouts — asides on a bid — apart from the bids around them. A callout
-- is a list item written wholly in italic and nested under the bid it explains,
-- such as `- _Note: always 3S, whichever M they bid_`. A list marker displays
-- its line as a round of the auction (spec.md #appearance), and a callout is
-- not itself a bid, so it must not carry a marker. The filter moves each
-- callout out of its list and into the item it annotates, as a div classed
-- `callout`, so the callout reads under that item's own text.
--
-- A callout must stand alone under the item it annotates. When it shares its
-- list with other items, or is nested under no item at all, nothing settles
-- which item it annotates or where it would sit, so the filter fails the render
-- rather than guess.

-- Whether a list item is a callout: one paragraph, italic from its first word
-- to its last. An item that merely opens on an italic term stays an ordinary
-- item.
local function is_callout(item)
  if #item ~= 1 then
    return false
  end
  local block = item[1]
  local is_paragraph = block.t == 'Plain' or block.t == 'Para'
  return is_paragraph
    and #block.content == 1
    and block.content[1].t == 'Emph'
end

-- Fail the render over a misplaced callout, quoting its opening so the author
-- can find it. `problem` finishes the sentence "but this one …".
local function reject_callout(item, problem)
  error(string.format(
    'a callout must stand alone under the item it annotates, but this one %s: '
      .. '"%s"',
    problem, pandoc.utils.stringify(item):sub(1, 80)))
end

-- When `block` is a list holding a callout, return that callout; otherwise
-- return nil. A callout that shares its list with other items fails the render.
local function nested_callout(block)
  if block.t ~= 'BulletList' then
    return nil
  end
  local callout = block.content:find_if(is_callout)
  if callout and #block.content > 1 then
    reject_callout(callout, 'shares its list with other items')
  end
  return callout
end

-- Move each callout nested under one of this list's items into that item.
local function absorb_callouts(list)
  for _, item in ipairs(list.content) do
    for index, block in ipairs(item) do
      local callout = nested_callout(block)
      if callout then
        item[index] = pandoc.Div(callout, { class = 'callout' })
      end
    end
  end
  return list
end

-- Fail the render over a callout left in a list after `absorb_callouts` has run
-- over the whole document. That pass moves every callout nested under an item,
-- so one left behind is nested under none and annotates nothing.
local function reject_stray_callout(list)
  local callout = list.content:find_if(is_callout)
  if callout then
    reject_callout(callout, 'is nested under no item')
  end
end

-- Two passes, so the check for strays sees the document only after
-- `absorb_callouts` has finished with all of it.
return {
  { BulletList = absorb_callouts },
  { BulletList = reject_stray_callout },
}
