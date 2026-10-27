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

- [ ] Analyze every combination within 30 seconds end to end, the user's
      fallback limit, or else cache the slow ones. The limit covers everything a
      problem takes: solving, then describing, shortening, and checking its
      lines.
  - Rationale: the user, 2026-10-27: the target is the end-to-end time. Timing
    the stages separately is still useful, to show where the time goes.
  - Note: solving alone runs past the limit for three of 12,336 targets sampled:
    KJ974 opposite a void for 1 trick takes 391 seconds, QT864 opposite a void
    for 1 trick 256, and 4 opposite KJ97 for 1 trick 39. The next slowest
    takes 7. All three hold one long hand against a void or a singleton, with
    eight cards missing and a target that lets declarer lose several tricks.
    Nearly all of their solving time goes to `Frontier::insert`, keeping huge
    frontiers free of beaten results.
  - Note: describing and checking can take far longer than solving: 4 opposite
    KJ97 for 1 trick takes over 600 seconds end to end. The rest of two samples,
    nearly 6,000 problems, took under 90 seconds in all; KJ974 and QT864
    opposite a void haven't been timed end to end.

---

## Line descriptions {#line-descriptions}

**Goal:** describe every line as briefly and faithfully as a teacher would.

- [ ] Bring more lines within the 400-character limit: shortened as spec.md
      #shortening-lines describes, 1,243 of the 2,652 sampled lines that ran
      past it still do.
  - Rationale: the user, 2026-10-22: a line must be accurate and complete above
    all else; a concise but misleading line is worse than none. Of the ways to
    show a complete but long line, the user chose the limit, then shortening.
  - Note: a teacher's further shorthand, such as "if an honor falls, cash the
    other one", would need conditions about cards fallen rather than who played
    them.
  - Note: parts whose lines read the same could share one condition where the
    "Otherwise" can't take them, as two of the usual case's four parts do for
    JT97 opposite K83 for 3 tricks.
- [ ] Describe the lines the check still rejects, which are shown as too many
      cases: 43 of 11,702 sampled problems, mostly a reply naming a card already
      played after branches that answered second hand differently, as in AQJ762
      opposite 93 for 4 tricks.
- [ ] Name each card once along a line where the reader can't tell why: "Low to
      the 9. If West wins with one of the K, Q, J, or East shows out, low to the
      T, then low to the T." for AT42 opposite 953 is accurate, since the first
      T only stays in hand where West's honor fell to the A, but reads oddly.
  - Note: naming each trick for its likeliest branch's cards was tried and
    dropped: it turned KQ964 opposite A852's safety play, "Cash the A, then low
    to the 9", into "Cash the A, then cash the K, then cash the Q, then cash the
    K".
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
- [ ] Name a ducked trick with a stated answer by the card it plays where that
      reads better: AT42 opposite 953 for 2 tricks says "duck a round (if West
      plays a low card, play the A)" for low to the A, ducking West's honors.
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
- [ ] Give remarks for lines without a finesse the conditions that need one:
      AQ8x opposite K9xx for 4 tricks, whose complete line cashes top cards
      unless someone shows out, says only "Play for the drop", where it once
      said "Finesse hoping the suit splits 3-2, or the J and T are split".
  - Note: conditions about where a card lies, such as "the J and T are split",
    come only with a finesse to set onside; one that fits either way round would
    serve a drop as well.
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
  - Note: the line that averages the most tricks can differ from the best line
    for every trick target. In K1084 opposite Q32, by Wikipedia's figures, the
    ten finesse makes 2 tricks 83.1% of the time and 3 tricks 28.7%, while the
    analyzer's best lines reach 85.93% and 31.83%, both of which SuitPlay
    confirms.
