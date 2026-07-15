# Convention card maker — tasks

Tracks pending follow-ups for `convention_cards/` (the BridgeWinners card +
reminders merge tool and its Streamlit webapp, deployed on Render at
https://ruffdraft.onrender.com).

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

- [ ] Set a custom favicon via `st.set_page_config(page_icon=...)` — deferred by
      the owner to revisit later.

## Reference

`verify_ui.mjs` drives the app end to end in a headless browser (upload, fill
reminders, generate, download) against either a local dev server or the live
deployment — run `npm install` once, then
`node verify_ui.mjs <app-url> <card-pdf-path>`.
