-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Require every bulleted list item to open with a line of its own text, as
-- every item of a tight list does. The stylesheet hangs each item's marker at
-- the start of the item's first line (`ul > li::before` in notes.css), so an
-- item that opens with anything else would strand its marker on a line of its
-- own. The usual cause is a loose list: blank lines between items make pandoc
-- wrap each item's text in a paragraph. Rather than guess at a layout for such
-- an item, the filter fails the render.

-- Name the block an item opens with, for the error message. A paragraph gets a
-- hint, since a loose list is the usual way an item comes to open with one.
local function describe_opening(block)
  if block.t == 'Para' then
    return 'a paragraph, as in a loose list with blank lines between items'
  end
  return 'a block of type ' .. block.t
end

-- Fail the render over an item that opens with anything but text, quoting the
-- item's opening so the author can find it.
local function require_text_openings(list)
  for _, item in ipairs(list.content) do
    -- `item[1]` is nil for an empty item, which passes: it has no text to keep
    -- beside its marker.
    local opening = item[1]
    if opening and opening.t ~= 'Plain' then
      local excerpt = pandoc.utils.stringify(item):sub(1, 80)
      error(string.format(
        'a list item must open with a line of its own text, but this one '
          .. 'opens with %s: "%s"',
        describe_opening(opening), excerpt))
    end
  end
end

return { BulletList = require_text_openings }
