-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Check the document's metadata block. The title feeds the `<title>` and the
-- title block atop the page, so the notes must carry one; make its absence an
-- error.

function Pandoc(document)
  local title = document.meta.title
  if not title or pandoc.utils.stringify(title) == '' then
    error('the notes need a non-empty `title` in their YAML metadata block')
  end
end
