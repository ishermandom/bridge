# Suit-combination analyzer tasks

Implementation queue for the design in [spec.md](spec.md).

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Pure suit combinations {#pure-combinations}

**Goal:** analyze any suit combination, with unlimited entries and nothing known
about the defenders' hands, well enough to reproduce every row of
`flashcards/input/suit_combinations.csv`: the success %, the best line in
English, and the intuition behind it.

- [~] Solver: the best line's chance of reaching the target against best
  defense.
- [ ] Describe the best line in English, beyond its first trick.
- [ ] Explain the intuition behind the line, such as "Finesse hoping the K is
      onside".
- [ ] Command-line tool, plus a comparison against every row of the input file.
- [ ] Speed: 5,000 entries like the input file's within a minute.
  - Note: the user set fallbacks if that proves impossible: first 10 minutes,
    then "any combination within 30 seconds". A relaxed target means queueing a
    task to cache results.
- [ ] Once every row of the input file works, extend the tests with
      progressively harder combinations, such as long suits and safety plays.
- [ ] Cross-check the solver against published data, such as worked examples in
      Wikipedia's "Suit combination" article.
- [ ] Check results against CCAnalyser, the user's reference tool
      (https://bridge.esmarkkappel.dk/main/main.html).
  - Note: drive a real browser (Playwright), never disguised, within the user's
    limits: at most 100 examples in all, 3 per minute, and 10 per 30 minutes.
    Stop for good at the first block or error rather than retry. A plain `curl`
    download was refused with HTTP 455 ("ModSecurity Action").
  - Note: the same limits cover SuitPlay's web version
    (https://jeroenwarmerdam.pythonanywhere.com/suitplay/home.html), a second
    reference.

---

## Backlog

- [ ] Wire the analyzer into the card generator (`anki/`), whose input file
      holds a hand-typed success %, line, and remarks today.
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
    best line for every trick target? No verified example yet; checking K1084
    opposite Q32's best lines for 2 and 3 tricks would answer it for that
    holding.
