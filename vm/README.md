# Linux virtual machine

A small Debian virtual machine that Lima runs for the repo's jobs that need
Linux and a screen of their own:

- **SuitPlay**, a Windows program, runs under Wine on the virtual display `:1`,
  for `suit_combinations` to compare its analyzer against.
  `suit_combinations/spec.md #suitplay` says why it needs Linux.
- **The ACBL fetch's browser** runs on the virtual display `:2`, driven by
  `session_analysis/cloudflare_fetching.py`. Cloudflare refuses headless
  browsers, so the browser needs a screen, and a virtual one spares the Mac the
  need for a logged in desktop session. A logged in Mac desktop session has two
  costs: it's some hassle on every reboot to log in; and it proved somewhat
  unstable to interact with the WindowServer over ssh for another account's UI
  session.

The two share one machine, since a second would cost several more gigabytes.

## Using it

Run `start.sh` before each use. The first run builds the machine, in about 4
minutes; later runs start it in seconds if it's stopped. Each prints the
machine's name, for `limactl`:

```shell
instance=$(bash vm/start.sh)
limactl shell "$instance" -- uname -a
```

Leave the machine running when done, since another job may be using it. It
powers itself off after 10 minutes with nothing to do, and each `start.sh`
restarts those 10 minutes, so its caller has the full time to begin work.

A command run through `limactl shell` counts as work while it runs. Two kinds of
work go unseen, and need wrapping in `keep-awake`, or the machine may power off
under them:

- **Work that outlives its shell**, as under `nohup` or `tmux`.
- **A command that sends both its output and its errors elsewhere**, as
  `suit_combinations/suitplay/run.sh` does.

```shell
limactl shell bridge -- keep-awake sh -c 'long-job > job.log 2>&1'
```

`idle-poweroff`'s header lists everything that counts as work. Each minute's
verdict goes to the machine's journal:

```shell
limactl shell bridge -- journalctl -u idle-poweroff
```

## Changing it

Lima reads `lima.yaml`, and every file named there, only when creating the
machine. To apply a change, delete the machine, and the next `start.sh` builds
it afresh. Deleting cuts off any job still using the machine, and SuitPlay asks
for its license again on the rebuilt one.

```shell
limactl delete --force bridge
```

## Why it works this way

- **The machine stops itself.** A client that stopped the machine after its own
  work could cut off another job mid-run, so clients only ever start it. A count
  of running clients, kept on the Mac, was the alternative, set aside once
  trials showed `idle-poweroff` reliable.
- **Each job has its own display.** SuitPlay's automation types into whichever
  window has keyboard focus, and a Chrome window on the same display could take
  that focus mid-run.
- **Downloads are pinned.** `setup.sh` checks Hangover, AutoHotkey, and Chrome
  for Testing against fixed digests, so a rebuilt machine runs what the last one
  did.

The trials behind this design are written up in
`/Users/Shared/data/bridge/acbl-fetch-freeze-2026-11/README.md`. They cover
Chrome clearing Cloudflare from the machine, and what `idle-poweroff` counts as
work.
