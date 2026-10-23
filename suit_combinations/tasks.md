# Suit-combination analyzer tasks

Implementation queue for the design in [spec.md](spec.md).

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Pure suit combinations {#pure-combinations}

**Goal:** analyze any suit combination, with unlimited entries and nothing known
about the defenders' hands, well enough to reproduce every row of
`flashcards/input/suit_combinations.csv`: the success %, the best line in
English, and the intuition behind it.

Worktree: `.claude/worktrees/card-combination-flashcards`, branch
`suit-combination-analyzer`, holds the analyzer, unlanded until the user reviews
it and gives the go-ahead.

- [~] Extend the tests with progressively harder combinations, such as long
  suits and safety plays, pinning answers CCAnalyser confirms.
- [-] Check results against CCAnalyser, the user's reference tool
  (https://bridge.esmarkkappel.dk/main/main.html).
  - Note: stopped for good, as agreed, at the first error. Six analyses all
    matched the analyzer exactly; the seventh, KT84-Q32@3, timed out in the
    driver waiting for a result after a reset, most likely a fault in the driver
    rather than a block. Resuming needs the user's go-ahead, and a new driver:
    the old one lived in a job's scratch folder, and should wait for the
    result's text to change rather than for a button to become visible. The
    matches: KQT-xxx@2 54.84%, KJxx-A9xx@3 100%, AQxxx-J9xx@5 32.78%,
    AQ8xx-J9xx@4 100%, KQxxx-AT9x@5 100%, and KT84-Q32@2 85.93%.
  - Note: drive a real browser (Playwright), never disguised, within the user's
    limits: at most 100 examples in all, 3 per minute, and 10 per 30 minutes.
    Stop for good at the first block or error rather than retry. A plain `curl`
    download was refused with HTTP 455 ("ModSecurity Action"); a real browser
    loads the page normally.
  - Note: CCAnalyser computes on its server, so each analysis is one request
    there. Its defaults match the analyzer's model: South on lead, 13 side
    entries each, no known side cards, and a 10 HCP cap that no suit exceeds.
- [x] Compare the analyzer with SuitPlay across a wide sample, looking for
      combinations that trip the analyzer up; `suitplay/` and `compare-suitplay`
      do the running and comparing, as spec.md #suitplay describes.
  - Note: SuitPlay 2.1.2 is a 32-bit Windows program with no web version. The
    user keeps it outside the repo, at
    `/Users/Shared/data/bridge/suitplay/SuitPlay.exe`. The user accepted its
    license agreement on 2026-10-20; a rebuilt machine shows it again, and one
    rebuild used `--accept-license` on the strength of that acceptance.
  - Rationale: the user treats SuitPlay as the gold standard. Newer analyzers
    that run locally, such as jdh8/suit-combination and Quaestio, didn't seem
    reliable enough to interest them.
  - Note: as of 2026-10-22, every compared target agreed: 16,438 targets across
    3,285 holdings, covering the spreadsheet's and tests' holdings, 772
    published holdings (bridgehands.com, Warmerdam's corrections to the Official
    Encyclopedia of Bridge, Pavlicek, Wikipedia and others), 1,492 random ones,
    and 1,000 balanced ones rich in the T to 7. SuitPlay rejects A opposite x
    and AQ opposite Qx, and an hour each wasn't enough for 4 opposite KJ97,
    QJ974 opposite a void, or KJ974 opposite a void; fifteen minutes wasn't
    enough for KJ76 opposite 94. Where a published figure disagreed, SuitPlay
    sided with the analyzer; `tests/suitplay_checks.rs` pins eight such cases.
  - Note: the runs' holdings and results are in the job's scratch folder
    (`/Users/claude-sandbox/.claude/jobs/a4e2783b/tmp/published/`):
    `suitplay_full.tsv` holds every holding at five minutes each, and
    `suitplay_timed_out.tsv` the 21 that timed out, rerun at an hour each, and
    `suitplay_tricky.tsv` the balanced ones. Most of those 21 had been waiting
    on a SuitPlay warning, which the script now dismisses.
- [ ] Solve every combination within 30 seconds, the user's fallback limit, or
      else cache the slow ones. Three of 12,336 targets sampled exceed it: KJ974
      opposite a void for 1 trick takes 391 seconds, QT864 opposite a void for 1
      trick 256, and 4 opposite KJ97 for 1 trick 39. The next slowest takes 7.
  - Note: all three hold one long hand against a void or a singleton, with eight
    cards missing and a target that lets declarer lose several tricks. Nearly
    all the time goes to `Frontier::insert`, keeping huge frontiers free of
    beaten results; balanced holdings rarely take a tenth of a second.

---

## Line descriptions {#line-descriptions}

**Goal:** describe every line as briefly and faithfully as a teacher would.

- [~] Follow every card second hand might play where the line can still win,
  rather than only the lowest and a show-out, and say how declarer answers each.
  Plays that only another card leads to go unmentioned today: AT98 opposite Kxxx
  for 4 tricks reads "Cash the A, then cash the K", which covers East's QJ
  doubleton, 3.39% of the line's 9.04%. When West's singleton honor drops
  instead, the line takes two finesses against East's honor, and says nothing of
  them.
  - Rationale: the user, 2026-10-22: a line must be accurate and complete above
    all else; a concise but misleading line is worse than none.
  - Note: conditions share the gap, since they name only the last defender's
    card: in AQTxxx opposite xxx for 5 tricks, "Cash the A, then low to the Q. …
    If it loses, cash the Q." reads as though the Q lost, but the losing branch
    is West's singleton K, ducked. The next three tasks likely follow from this
    one.
- [ ] Name each card once along a line: 53 of 11,702 sampled lines name one
      twice, such as "Low to the 9, then low to the T, then low to the T" for
      AT42 opposite 953 for 2 tricks. One play answers second hand's different
      cards with different cards, as KQ964 opposite A852 plays the 6 over West's
      3 and the 9 over West's 7, and the line names only one of them.
  - Note: naming each trick for its likeliest branch's cards was tried and
    dropped: it turned KQ964 opposite A852's safety play, "Cash the A, then low
    to the 9", into "Cash the A, then cash the K, then cash the Q, then cash the
    K". Answering show-outs with the line's own card fixed most cases, from 210
    of 11,702.
- [ ] Lead and follow with the lowest of equal choices: AKT8 opposite 532 for 3
      tricks reads "Lead the 5 to the A" where "Cash the A" plays the same, and
      Q7 opposite AJ8642 for 5 tricks "Lead the Q and play the 6" where "Run the
      Q" does.
  - Note: preferring the lower card among ties, in the candidates' preference,
    was tried and dropped: reordering the candidates changes which plays the
    describer tries at all, and it lost KQ964 opposite A852's safety play. A fix
    could rename a play only among ones whose lines read the same.
- [ ] Offer "Either" only for lines that read differently: K975 opposite AT86
      for 4 tricks offers "Cash the K, then cash the A" and "Cash the A, then
      cash the K", which differ only in plays the line leaves out.
- [ ] Shorten lines that branch on every show-out, such as KJxx opposite A9xx
      for 3 tricks, which mostly comes down to cashing the K and then leading
      low toward the A9, inserting the 9, yet the analyzer spells out every
      branch.
  - Note: dropping the parts of a split that few deals reach doesn't work: in
    KQxxx opposite AT9x for 5 tricks, the rare 4-0 splits are the whole point of
    the safety play, and the shortened line, "cash the K, then cash the A, then
    cash the Q", would lose to them.
  - Note: answering a show-out with the line's own card, when that works, merged
    most show-out branches into the main line: sampled lines needing an outline
    fell from 487 to 163 of 11,702. KJxx opposite A9xx still splits.
- [ ] Find a condition for remarks that now name only a technique, such as
      "Finesse" for A1042 opposite 953, or "Repeated finesse" for K1084 opposite
      Q32 for 3 tricks: no condition built from three facts comes within 10% of
      where the line wins.
  - Note: facts about a defender's length, such as "West holds at least four",
    were tried and dropped: they explained only three more of 70 random
    combinations, in awkward words such as "hoping the 8 is onside and East
    holds at least five, plus 11.51% more", and slowed the 5,000-entry benchmark
    from 1.9 to 3.1 seconds.
  - Note: more remarks name only a technique since a condition must miss less
    than saying nothing would, as spec.md #remarks says: 227 of 11,702 sampled
    remarks, most for lines under 10%, lost a condition such as "hoping West
    holds all seven" that held in almost none of their wins.
- [ ] Name the defender, not "onside" or "offside", for an honor the line drops
      rather than finesses: QT85 opposite A742 for 4 tricks gets "Finesse hoping
      the K is singleton offside", where the A drops East's singleton K before
      the finesses against West.
- [ ] Name the technique correctly when one hand is void: AKT74 opposite a void
      for 3 tricks gets "Finesse hoping the suit splits 4-4, plus 7.34% more",
      though with nothing to lead from in the other hand no finesse is possible;
      the line ducks a round first.

---

## Backlog

- [ ] Wire the analyzer into the card generator (`anki/`), whose input file
      holds a hand-typed success %, line, and remarks today.
  - Note: `suit_combinations -` reads one problem per line of standard input, so
    the generator can analyze a whole file in one process.
- [ ] The constraints `flashcards/tasks.md` #suit-combination-constraints queues
      for the cards. CCAnalyser takes most of them: the hand on lead, side
      entries to each hand, each defender's known cards in other suits, and each
      defender's maximum HCP.
  - Note: limited entries make the hand each trick is won in matter, which the
    unlimited-entries model ignores.
- [ ] A most-tricks-on-average goal, beside the chance of a target.
  - Note: a test case for goals. In K1084 opposite Q32, finessing the 10
    averages the most tricks (2.12), yet a deeper finesse of the 8 beats it on
    more layouts (22.95% to 18.33%); in K1087 opposite Q32, eight lines beat
    each other in a circle, so the best matchpoint strategy picks one at random
    (Wikipedia, "Suit combination").
  - Open question: can the line that averages the most tricks differ from the
    best line for every trick target? Likely yes for K1084 opposite Q32: by
    Wikipedia's figures, the ten finesse makes 2 tricks 83.1% of the time and 3
    tricks 28.7%, while the analyzer's best lines reach 85.93% and 31.83%.
    CCAnalyser confirmed the 85.93%; its check of 3 tricks timed out, so that
    target is still open.
