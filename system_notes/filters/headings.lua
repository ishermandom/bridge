-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Cross-references. Every link to a heading gains the `xref` class, so print
-- CSS can append the page number, and a link left empty — `[](#section-id)` —
-- also takes the heading's title for its text. Each link must target a
-- heading that exists; an unknown target is an error, so a typo cannot ship
-- as a dead link.
--
-- Heading levels must not skip — no `###` directly under a `#`, no `##`
-- before the first `#`: a skip is an authoring slip, an outline claiming a
-- depth that has no parent.

-- Each heading's title, by the heading's id.
local titles_by_id = {}
local previous_level = 0

-- The heading's text as a title for copying elsewhere: links reduced to
-- their text (a copied link would nest inside the reference link) and
-- footnotes dropped (a copied footnote would appear twice).
local function title_of(heading)
  return heading.content:walk({
    Link = function(link)
      return link.content
    end,
    Note = function()
      return {}
    end,
  })
end

-- Remember a heading's title, checking that its level does not skip.
local function record_heading(heading)
  if heading.level > previous_level + 1 then
    error(string.format(
      'heading "%s" is level %d but follows a level %d heading; levels must '
        .. 'not skip',
      pandoc.utils.stringify(heading.content), heading.level, previous_level))
  end
  previous_level = heading.level
  titles_by_id[heading.identifier] = title_of(heading)
end

local function make_cross_reference(link)
  if link.target:sub(1, 1) ~= '#' then
    return nil
  end
  local title = titles_by_id[link.target:sub(2)]
  if not title then
    error('unknown cross-reference target: ' .. link.target)
  end
  if #link.content == 0 then
    link.content = title
  end
  link.classes:insert('xref')
  return link
end

function Pandoc(document)
  document:walk({ Header = record_heading })
  document = document:walk({ Link = make_cross_reference })
  return document
end
