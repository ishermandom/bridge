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
  - Note: the same limits cover SuitPlay's web version
    (https://jeroenwarmerdam.pythonanywhere.com/suitplay/home.html), a second
    reference.

---

## Line descriptions {#line-descriptions}

**Goal:** describe long and safety-play lines as briefly as a teacher would, now
that every one is complete and unambiguous.

- [ ] Shorten lines that branch on every show-out, such as KJxx opposite A9xx
      for 3 tricks, which mostly comes down to cashing the K and then leading
      low toward the A9, inserting the 9, yet the analyzer spells out every
      branch.
  - Note: dropping the parts of a split that few deals reach doesn't work: in
    KQxxx opposite AT9x for 5 tricks, the rare 4-0 splits are the whole point of
    the safety play, and the shortened line, "cash the K, then cash the A, then
    cash the Q", would lose to them.
- [ ] Find a condition for remarks that now name only a technique, such as
      "Finesse" for A1042 opposite 953, or "Repeated finesse" for K1084 opposite
      Q32 for 3 tricks: no condition built from three facts comes within 10% of
      where the line wins.
  - Note: facts about a defender's length, such as "West holds at least four",
    were tried and dropped: they explained only three more of 70 random
    combinations, in awkward words such as "hoping the 8 is onside and East
    holds at least five, plus 11.51% more", and slowed the 5,000-entry benchmark
    from 1.9 to 3.1 seconds.

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
