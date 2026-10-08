# Tasks — system notes renderer

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

Design decisions live in `spec.md`; this file tracks the work.

## Typography

**Goal:** settle how the notes look before the stylesheet hardens.

- Open question {#wide-overflow}: should a section taller than even a full wide
  page flow onto following pages (today's behavior — three fixture sections do)
  or fail the render, forcing the author to split the section? Surfaced
  2026-09-12 by the render's new page-count guard, which tolerates the flow
  whenever a wide section exists.
- Open question: should the table of contents' title take the section-heading
  style (accent color, italic) and set the running page header? Since 2026-09-26
  it is an h2, a structural peer of the top-level sections, but it keeps its own
  plain look and stays out of the running header.

- [ ] **Explore serif alternatives to IBM Plex Serif** {#serif-alternatives} —
      render the fixture in a few more open-licensed serifs and compare on paper
      at 11pt, against the letterform preferences in `spec.md` #appearance.
  - Note: Plex Serif is the working choice; Inter and Open Sans are the recorded
    sans-serif fallbacks. The prototype's per-font sample renderer
    (`bridge-private/scratch/system_notes_prototype/font_samples/`) is the
    starting point.
  - Note: a new body face means a new italic angle, and the suit skew in
    `notes.css` must follow — enforced by
    `test_suit_skew_tracks_the_body_font_italic_angle`, which fails until the
    stylesheet matches the installed italic.

---

## Backlog

- [ ] **Spike: Typst as the PDF engine** {#typst-spike} — render the fixture
      from the same `notes.md` via pandoc's Typst writer and a template that
      packs sections natively (`measure()` plus scripted placement), and compare
      against the WeasyPrint output.
  - Rationale: the packing WeasyPrint leaves to `print_layout.py` is a
    first-class layout concern in Typst, and this is the second WeasyPrint
    limitation engineered around (after `column-span: all`). Escape hatch if
    quirks keep accumulating; switching costs a second styling system beside the
    CSS, plus Typst branches in the notation filters.
- [ ] **Pack pandoc's footnote endnotes** {#pack-footnotes} — pandoc writes the
      endnotes as a `<section id="footnotes">` after the last section, so they
      already stand in `<main>` beside the other sections, but `paged_document`
      refuses documents with footnotes. Pack the endnotes as the last section to
      lift the refusal.
  - Note: the endnotes open with a rule rather than a heading, so a block of
    them taller than a column needs its own answer for a wide page, which sets
    the heading across the page.
- [ ] **Per-level list markers in the source** {#source-list-markers} — an
      autoformatter giving each indentation depth its own list marker, so the
      Markdown source reads like the rendered page.
  - Note: Markdown has only three unordered markers (`-`, `*`, `+`), which
    pandoc treats identically, so markers would cycle below three levels — and
    prettier normalizes all three to `-` (verified with prettier 3.9), so the
    repo's Markdown formatting hook would undo them; the formatter must exclude
    these files or run after it.

- [~] **Read the Lua filters for readability as a set** {#lua-readability} —
  Ilya asked (2026-09-21) whether the filters could read better overall, and
  chose to take it up after the branch lands (2026-09-25).
  - Worktree: `lua-readability`
  - Open question: keep the filters in Lua or port them to Python. Pandoc's
    Python libraries lag its releases. A Python comparison of `sections.lua`
    showed its difficulty was structure rather than language; the filter has
    since given way to pandoc's own sections (2026-09-25).
  - Note: the grammar version of `bids.lua` and both `headings.lua` changes, the
    heading-map cleanup and the preamble rule, landed ahead of Ilya's own
    reading of those files, which this task still covers. The entry point
    `check_headings_and_resolve_cross_references` is a long name worth a look
    then (2026-09-26).
  - Open question: the scanning loop `bids.lua` and `shorthand.lua` shared gave
    way to the grammar in `bids.lua`, so only `shorthand.lua` keeps it. Should
    `shorthand.lua` become a grammar too? Ilya wants to look more closely first
    (2026-09-26).
  - Open question: whether a `lua.md` rules file has enough to say. Candidates:
    Lua's way to follow the regex-decomposition rule (`re` grammars, as
    `bids.lua` now uses), the byte and locale traps in Lua's string functions,
    and returning the filter table. Ilya deferred the call (2026-09-25).
  - Note: deferred (2026-09-25): a formatter (StyLua) and a linter (luacheck or
    selene) for the Lua files.
  - Note: type annotations declined (2026-09-25): Lua has no type syntax, pandoc
    publishes no type definitions for its Lua functions, and the tests already
    run every filter through pandoc.

- [ ] **Decide whether and where references carry page numbers** {#page-numbers}
      — every link to a heading is page-numbered in print today, as "(p. N)"
      after its text. The numbers down the table of contents are not in
      question, since a printed table of contents with no page numbers has
      nothing to point with, and section headings carry no numbers of their own
      either way.
  - Open question: whether the "(p. N)" stays at all. Ilya deferred the call
    (2026-09-07), having seen only the HTML then; the PDF now shows what it
    looks like.
  - Open question: if it stays, which links carry one. Today every link does,
    which would put "(p. 7)" on each of the six `[MTB](#mtb)` mentions in the
    Callahan notes. Telling a pointer from a mention needs something the author
    writes — a pandoc link attribute, say — weighed against keeping the notation
    tiny.
  - Open question: whether the empty-link form earns its place. Ilya has never
    written one, and it expands to the full heading title where his lines
    abbreviate (2026-09-21).
  - Note: a `term` class keyed on whether the author typed the link text was
    tried and dropped: it styled `[Stayman](#stayman)` and `[](#stayman)`
    differently though both render "Stayman", and it fired on all 26 links in
    the Callahan notes, none of which is empty.

- [~] **Stop the test run crashing in Pango's font cleanup**
  {#pango-cleanup-crash} — the repo's test run intermittently dies of a
  segmentation fault when Python's garbage collector frees a Pango font map that
  WeasyPrint created, and Pango's cleanup crashes inside HarfBuzz. Every test
  may have passed by then, so the Stop hook halts a turn over a run with no
  failing test in it.
  - Worktree: `pango-cleanup-crash`
  - Rationale: hit twice on 2026-10-07, in the bridge transcript-format lane.
    The first run stopped right after `render_notes_test.py`, the run's last
    file, with every test passed and neither a summary line nor a trace — likely
    the same crash at exit, once pytest's crash reporter is off. Six reruns then
    passed. The second crashed during
    `test_every_printed_page_reference_is_correct`, while
    `pdf_inspection.heading_pages` read a rendered PDF, and left the trace
    below.
  - Note: the libraries in the trace are Homebrew's Pango 1.58.2, HarfBuzz
    14.5.0 and GLib 2.90.0, under Homebrew's Python 3.14.7. Whether the fault
    lies in Pango's font-map finalizer, in a mismatch between those libraries,
    or in how WeasyPrint leaves the font map to Python's collector is unknown.
  - Note: the trace, as printed, with pytest's and pluggy's own frames left out:

    ```text
    Fatal Python error: Segmentation fault

    Current thread 0x00000001f6caa180 (most recent call first):
      Garbage-collecting
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_data_structures.py", line 249 in read_from_stream
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_data_structures.py", line 1559 in read_object
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_data_structures.py", line 622 in read_from_stream
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_data_structures.py", line 1556 in read_object
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/_reader.py", line 422 in _get_object_from_stream
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/_reader.py", line 470 in get_object
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_base.py", line 388 in get_object
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/generic/_base.py", line 959 in is_null_or_none
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/_reader.py", line 226 in root_object
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/_doc_common.py", line 861 in _get_outline
      File "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/pypdf/_doc_common.py", line 851 in outline
      File "/Users/Shared/code/bridge/system_notes/pdf_inspection.py", line 70 in heading_pages
      File "/Users/Shared/code/bridge/system_notes/render_notes_test.py", line 341 in _heading_pages_by_stripped_key
      File "/Users/Shared/code/bridge/system_notes/render_notes_test.py", line 378 in test_every_printed_page_reference_is_correct
      [pytest and pluggy frames left out]

    Current thread's C stack trace (most recent call first):
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _Py_DumpStack+0x44 [0x104f92e5c]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at faulthandler_dump_c_stack+0x58 [0x104fa584c]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at faulthandler_fatal_error+0x140 [0x104fa5710]
      Binary file "/usr/lib/system/libsystem_platform.dylib", at _sigtramp+0x38 [0x18a275744]
      Binary file "/opt/homebrew/Cellar/harfbuzz/14.5.0/lib/libharfbuzz.0.dylib", at _ZN2OT8GSUBGPOS13accelerator_tINS_6Layout4GPOSEED2Ev+0x60 [0x111c35a00]
      Binary file "/opt/homebrew/Cellar/harfbuzz/14.5.0/lib/libharfbuzz.0.dylib", at _ZN16hb_lazy_loader_tIN2OT18GPOS_accelerator_tE21hb_face_lazy_loader_tIS1_Lj27EE9hb_face_tLj27ES1_E10do_destroyEPS1_+0x20 [0x111c34fe0]
      Binary file "/opt/homebrew/Cellar/harfbuzz/14.5.0/lib/libharfbuzz.0.dylib", at _ZN12hb_ot_face_t4finiEv+0x1d8 [0x111c5e2c4]
      Binary file "/opt/homebrew/Cellar/harfbuzz/14.5.0/lib/libharfbuzz.0.dylib", at hb_face_destroy+0x9c [0x111caadf8]
      Binary file "/opt/homebrew/Cellar/pango/1.58.2/lib/libpangoft2-1.0.0.dylib", at pango_fc_font_face_data_free+0x34 [0x111544a88]
      Binary file "/opt/homebrew/Cellar/glib/2.90.0/lib/libglib-2.0.0.dylib", at g_hash_table_remove_all_nodes+0xf0 [0x1116ad5ec]
      Binary file "/opt/homebrew/Cellar/glib/2.90.0/lib/libglib-2.0.0.dylib", at g_hash_table_remove_all+0x38 [0x1116ad70c]
      Binary file "/opt/homebrew/Cellar/glib/2.90.0/lib/libglib-2.0.0.dylib", at g_hash_table_destroy+0x18 [0x1116ad6b4]
      Binary file "/opt/homebrew/Cellar/pango/1.58.2/lib/libpangoft2-1.0.0.dylib", at pango_fc_font_map_fini+0x60 [0x11154078c]
      Binary file "/opt/homebrew/Cellar/pango/1.58.2/lib/libpangoft2-1.0.0.dylib", at pango_fc_font_map_shutdown+0x64 [0x111541120]
      Binary file "/opt/homebrew/Cellar/pango/1.58.2/lib/libpangoft2-1.0.0.dylib", at pango_fc_font_map_finalize+0x14 [0x111541854]
      Binary file "/opt/homebrew/Cellar/pango/1.58.2/lib/libpangoft2-1.0.0.dylib", at pango_ft2_font_map_finalize+0x30 [0x111545f9c]
      Binary file "/opt/homebrew/Cellar/glib/2.90.0/lib/libgobject-2.0.0.dylib", at g_object_unref+0x234 [0x1114e3678]
      Binary file "/usr/lib/libffi.dylib", at ffi_call_SYSV+0x50 [0x19ea34050]
      Binary file "/usr/lib/libffi.dylib", at ffi_call_int+0x4c4 [0x19ea3d5b8]
      Binary file "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/_cffi_backend.cpython-314-darwin.so", at cdata_call+0x388 [0x111241048]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _PyObject_MakeTpCall+0x78 [0x104dcf158]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at object_vacall+0x144 [0x104dd1d20]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at PyObject_CallFunctionObjArgs+0x38 [0x104dd1e44]
      Binary file "/Users/Shared/code/bridge/.venv/lib/python3.14/site-packages/_cffi_backend.cpython-314-darwin.so", at gcp_finalize+0x38 [0x111243848]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at gc_collect_main+0x970 [0x104f3f494]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _Py_HandlePending+0x60 [0x104f46c20]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _PyEval_EvalFrameDefault+0x3d64 [0x104f00a54]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _PyEval_Vector+0x108 [0x104efc998]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at PyObject_CallOneArg+0x6c [0x104dd021c]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _PyObject_GenericGetAttrWithDict+0x2c4 [0x104e3fedc]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at PyObject_GetAttr+0x3c [0x104e3f3b8]
      Binary file "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/Python", at _PyEval_EvalFrameDefault+0xa338 [0x104f07028]
      <truncated rest of calls>

    Extension modules: PIL._imaging, greenlet._greenlet, _brotli, charset_normalizer.md, charset_normalizer.cd, PIL._imagingft, numpy._core._multiarray_umath, numpy.linalg._umath_linalg, numpy.random._common, numpy.random.bit_generator, numpy.random._bounded_integers, numpy.random._pcg64, numpy.random._generator, numpy.random._mt19937, numpy.random._philox, numpy.random._sfc64, numpy.random.mtrand, kiwisolver._cext, PIL._imagingmath, PIL._imagingcms, fontTools.misc.bezierTools, _cffi_backend, fontTools.varLib.iup, PIL._avif, PIL._webp (total: 25)
    ```
