# Convention card maker — tasks

Tracks pending follow-ups for `convention_cards/` (the BridgeWinners card +
reminders merge tool and its Streamlit webapp, deployed on Render at
https://ruffdraft.onrender.com).

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Reference

`verify_ui.mjs` drives the app end to end in a headless browser (upload, fill
reminders, generate, download) against either a local dev server or the live
deployment — run `npm install` once, then
`node verify_ui.mjs <app-url> <card-pdf-path>`.

---

## Backlog

- [ ] **Set the reminder strip in a repo font** {#reminder-strip-font} — replace
      the strip's Helvetica, which the PDF never embeds (each viewer or printer
      substitutes its own), with Source Sans 3 Regular and Bold from the repo's
      `fonts/`. Scale the sizes by Helvetica's larger x-height: items 6.5pt to
      7pt, section headers 7.5pt to 8pt, fold labels 5.5pt to 6pt.
  - Rationale: measured 2026-11-04 against every partner's reminders, Source
    Sans 3 at 7pt matches Helvetica at 6.5pt in x-height (3.40pt) and runs 0.99×
    its width, so every column fits exactly as before.
  - Note: the Render service already roots at the repo (re-rooted and verified
    2026-11-05), so the deployed app can read `fonts/`. Its commands run inside
    `convention_cards/`, where Streamlit finds `.streamlit/config.toml`, and
    build filters limit auto-deploys to `convention_cards/**` and `fonts/**`.
    Record those settings in the README's deploy paragraph as part of this
    change, since the dashboard is otherwise their only record.
