-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Wrap each top-level section — its heading and everything up to the next
-- top-level heading — in a div classed `section`, and the whole run of
-- sections in one div classed `sections`. The wrappers are the markers
-- print_layout.py keys on when it packs whole sections onto explicit
-- printed pages (spec.md #section-packing); on screen they carry no styling.
--
-- The wrappers are raw HTML rather than pandoc divs: pandoc's HTML writer
-- turns a div that opens with a heading into a `<section>` and moves the
-- heading's id onto it. Raw HTML also costs the text rendering nothing: the
-- plain-text writer drops it.

local function raw(html)
  return pandoc.RawBlock('html', html)
end

function Pandoc(document)
  local blocks = pandoc.Blocks({})
  local is_section_open = false
  for _, block in ipairs(document.blocks) do
    if block.t == 'Header' and block.level == 1 then
      if is_section_open then
        blocks:insert(raw('</div>'))
      else
        blocks:insert(raw('<div class="sections">'))
      end
      blocks:insert(raw('<div class="section">'))
      is_section_open = true
    end
    blocks:insert(block)
  end
  if is_section_open then
    blocks:insert(raw('</div>'))
    blocks:insert(raw('</div>'))
  end
  document.blocks = blocks
  return document
end
