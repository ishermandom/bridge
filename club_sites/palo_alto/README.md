# Palo Alto Bridge Center reservations helper

A [Tampermonkey](https://www.tampermonkey.net/) userscript that adds
conveniences to the reservations page at
`https://paloaltobridge.org/reservations/`. It prefills your saved details on
the reservation, lookup, and cancellation forms, shows the full game list
expanded by default, and visually distinguishes limited games (such as EZ
Bridge) from open ones so they are harder to book by accident.

## What it does

- **Remembers you.** Prefills your name when you make a reservation and when you
  look up your reservations, and your email when you cancel one — so you don't
  retype them each time.
- **Prefills your playing direction.** Sets the direction preference to
  East/West when you reserve. You can still change it.
- **Defaults the section to "Open".** When a game offers a section choice, it
  pre-selects "Open" — still editable if you ever want another section.
- **Expands the full game list.** Opens the "Show more games" section
  automatically, so every game is visible without an extra click.
- **Flags limited games.** Marks limited games — such as EZ Bridge — in the game
  list and again in the reservation dialog, so you're unlikely to book one by
  accident. It's a visual warning only; it never blocks a booking.
- **Hides the Firecracker fireworks.** Suppresses the animated fireworks the
  site draws during the Firecracker sectional.

A game counts as "limited" when it carries a masterpoint ceiling — the
eligibility cap the site places on restricted games like EZ Bridge, a `0-99`
pairs game, or a `0-3000` Mid-Flight event. Open games carry no ceiling.

## Install

1. Install the **Tampermonkey** extension from the Chrome Web Store.
2. On Tampermonkey's details page (`chrome://extensions` → Tampermonkey →
   Details), turn on **"Allow user scripts."** As of Chrome 138 this
   per-extension toggle replaced the old global Developer Mode requirement.
3. On the same page, set **Site access → On specific sites** and add
   `https://paloaltobridge.org`. This limits Tampermonkey to just this site
   instead of all your browsing. (The only features this disables — automatic
   update checks and cross-site requests — aren't used here.)
4. Open `pabc-reservations.user.js` from this directory and paste its contents
   into a new script in the Tampermonkey dashboard, then save.

Reload the reservations page and the conveniences take effect.

## Configure your profile

Your name, email, and playing direction are set through an in-page settings
panel: open it from the control the script adds to the reservations page, fill
in the three fields, and save. The values are stored locally by Tampermonkey and
persist across visits; nothing is sent anywhere beyond the reservation forms you
submit yourself.

## Browser support

Chrome is the target. The script uses only the standard userscript (`GM_*`) API,
so it also runs unchanged under Tampermonkey on Firefox, Edge, or Safari, or
under other compatible managers — but those aren't actively tested.
