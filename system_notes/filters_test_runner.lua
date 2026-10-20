-- Copyright 2026 Ilya Sherman (ishermandom@)
-- SPDX-License-Identifier: MIT

-- The pandoc side of `filters_test.py`: applies one Lua filter per request, so
-- the tests share a single pandoc process instead of each launching its own.
--
-- Run as `pandoc lua filters_test_runner.lua`. Each line of standard input is
-- one request, a JSON object with three fields:
--
-- - `filter`: the filter's path
-- - `format`: the output format, which the filter also sees as `FORMAT`
-- - `markdown`: the input
--
-- Each request gets one line of JSON back: `{"output": …}` holding what
-- `pandoc --wrap=none --lua-filter FILTER --to FORMAT` would print, or
-- `{"error": …}` holding the message the filter raised — the command line's
-- message without its `Error running filter` prefix. The loop ends when
-- standard input closes.

for line in io.lines() do
  local request = pandoc.json.decode(line, false)

  -- A filter runs with the table it is given as its whole environment, so the
  -- table falls back to the real globals for everything but FORMAT. A fresh
  -- table per request keeps the globals one run defines out of the next, as
  -- separate processes would.
  local environment =
    setmetatable({ FORMAT = request.format }, { __index = _ENV })

  local succeeded, result = pcall(function()
    local document = pandoc.read(request.markdown, 'markdown')
    document =
      pandoc.utils.run_lua_filter(document, request.filter, environment)
    local text =
      pandoc.write(document, request.format, { wrap_text = 'none' })
    -- The command line ends non-empty output with a newline wherever the writer
    -- has not already, so this does too.
    if text ~= '' and text:sub(-1) ~= '\n' then
      text = text .. '\n'
    end
    return text
  end)

  local reply = succeeded and { output = result }
    or { error = tostring(result) }
  io.write(pandoc.json.encode(reply), '\n')
  -- Standard output is a pipe, so it is buffered; the test waits on this line.
  io.stdout:flush()
end
