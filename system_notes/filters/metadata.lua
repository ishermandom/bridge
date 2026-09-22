-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- Check the document's metadata block. The title feeds the page header, the
-- `<title>`, and the PDF's metadata, so its absence would ship a blank header
-- on every page rather than fail; make it an error instead.

function Pandoc(document)
  local title = document.meta.title
  if not title or pandoc.utils.stringify(title) == '' then
    error('the notes need a non-empty `title` in their YAML metadata block')
  end
end
