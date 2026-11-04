-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Turn each TODO paragraph into a TODO callout, set apart from the agreements
-- around it. A TODO paragraph marks an open item, something the partnership has
-- yet to settle. It stands on its own, not inside a list, and opens with the
-- word `TODO:`, capitals and colon both:
--
--     TODO: Fill in the response steps
--
-- The filter wraps such a paragraph in a div classed `todo-callout`, which the
-- stylesheet draws as a tinted panel, and turns its opening `TODO:` into the
-- callout's label: the word `TODO` in a span classed `todo-label`. The colon
-- goes, since the panel already sets the paragraph apart.
--
-- The plain-text rendering keeps the paragraph exactly as typed, where `TODO:`
-- already marks it.

-- Whether a block is a paragraph whose first word is exactly `TODO:`. Where the
-- paragraph stands is for `convert_todo_paragraphs` to judge.
local function is_todo_paragraph(block)
  return block.t == 'Para'
    and #block.content > 0
    and block.content[1].t == 'Str'
    and block.content[1].text == 'TODO:'
end

-- Wrap a TODO paragraph in its callout, with the label in place of its opening
-- `TODO:`. The space after `TODO:` stays, so the label and the text read as
-- separate words.
local function make_todo_callout(paragraph)
  paragraph.content[1] =
    pandoc.Span({ pandoc.Str('TODO') }, { class = 'todo-label' })
  return pandoc.Div({ paragraph }, { class = 'todo-callout' })
end

-- Walk only the document's own blocks, never a list's, so a list item that
-- opens with `TODO:` stays an ordinary item.
local function convert_todo_paragraphs(document)
  if FORMAT == 'plain' then
    return nil
  end
  document.blocks = document.blocks:map(function(block)
    if is_todo_paragraph(block) then
      return make_todo_callout(block)
    end
    return block
  end)
  return document
end

return {
  { Pandoc = convert_todo_paragraphs },
}
