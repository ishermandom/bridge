# Suit-combination analyzer tasks

Implementation queue for the design in [spec.md](spec.md).

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` dropped

## Pure suit combinations {#pure-combinations}

**Goal:** analyze any suit combination, with unlimited entries and nothing known
about the defenders' hands, well enough to reproduce every row of
`flashcards/input/suit_combinations.csv`: the success %, the best line in
English, and the intuition behind it.

- [ ] High priority: review the Rust code in `unreviewed/`, then move it back up
      into `suit_combinations/` {#rust-review}.
  - Note: Cargo.toml and rustfmt.toml are already reviewed.
- [ ] Bring the code's terms in line with the spec's {#code-terms}: spec.md
      #search speaks of positions, continuations, winning layouts, frontier
      entries, and one entry strictly dominating another. The code calls an
      entry a "result" (`Frontier::results`, `BestResult` in `analysis.rs`, many
      comments in `solver.rs`) and the matching-or-beating test `covers`.
      "Result" also collides with Rust's own `Result` type.
  - Open question: the code's name for an entry. The user prefers the plain "set
    of winning layouts" in the spec, and a shorter name may suit the code.
  - Note: spec.md #positions calls the state at any moment of the play a
    position. The code's `Position` is only the state at the start of a trick,
    and a trick in progress is a `Trick`.

- [ ] Analyze every combination within 30 seconds end to end {#time-limit}, the
      user's fallback limit, or else cache the slow ones. The limit covers
      everything a problem takes: solving, then describing, shortening, and
      checking its lines.
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
  - Note: tried and dropped, 2026-10-31, on 3 opposite QT86 for 1 trick: keeping
    the first target's whole set in `Signature` instead of its 64-bit fold. The
    whole set turned away 98% of the fold's false passes (4.9 million passes
    against 228 million, of 15.1 billion quick tests, 4.15 million confirmed),
    yet ran 9.3 seconds against 7.3. Testing it without an early exit changed
    nothing, and padding the fold to the same 32 bytes cost only about 2%, so
    the cost is the extra work per test. The lever is fewer quick tests, such as
    indexing entries so most pairs are never compared.
  - Note: inside `Frontier::insert`, the size half of `Signature` never rules a
    pair out: the frontier is sorted by size, and each loop already sits on the
    side where the size test passes.
  - Note: the user, 2026-10-31: leave other folds open to explore, such as a
    128-bit fold, if that width matches the hardware.

---

## Line descriptions {#line-descriptions}

**Goal:** describe every line as briefly and faithfully as a teacher would.

- [ ] Bring more lines within the 400-character limit {#line-length}: shortened
      as spec.md #shortening-lines describes, 1,243 of the 2,652 sampled lines
      that ran past it still do.
  - Note: of those 2,652 lines, the usual case as "Otherwise" alone brought 810
    within the limit, and removing the most parts brought 1,409.
  - Rationale: the user, 2026-10-22: a line must be accurate and complete above
    all else; a concise but misleading line is worse than none. Of the ways to
    show a complete but long line, the user chose the limit, then shortening.
  - Note: a teacher's further shorthand, such as "if an honor falls, cash the
    other one", would need conditions about cards fallen rather than who played
    them.
  - Note: parts whose lines read the same could share one condition where the
    "Otherwise" can't take them, as two of the usual case's four parts do for
    JT97 opposite K83 for 3 tricks.
- [ ] Describe the lines the check still rejects {#rejected-lines}, which are
      shown as too many cases: 43 of 11,702 sampled problems, mostly a reply
      naming a card already played after branches that answered second hand
      differently, as in AQJ762 opposite 93 for 4 tricks.
  - Note: a smaller case, of another kind, found 2026-10-31: 86 opposite JT74
    for 1 trick reads "Run the 6. If East plays the A, the K, the Q, the 9, the
    5 or a low card, run the 8, then lead the J.", well within the length limit,
    and the check finds it stops short, with no trick won, in 184,756 deals.
- [ ] Name each card once along a line where the reader can't tell why: "Low to
      the 9. If West wins with one of the K, Q, J, or East shows out, low to the
      T, then low to the T." for AT42 opposite 953 is accurate, since the first
      T only stays in hand where West's honor fell to the A, but reads oddly.
  - Note: the AT42 opposite 953 quote no longer matches the analyzer's output at
    any target (checked 2026-10-27); find a current example, or confirm the
    problem is gone, before starting.
  - Note: naming each trick for its likeliest branch's cards was tried and
    dropped: it turned KQ964 opposite A852's safety play, "Cash the A, then low
    to the 9", into "Cash the A, then cash the K, then cash the Q, then cash the
    K".
- [ ] Describe AQT opposite xx for 3 tricks the way a teacher would
      {#adapting-finesses}: "Take two finesses against West, the T first."
      Today's line, "Low to the T. If West plays the K or the J, low to the T.
      Otherwise, low to the Q.", is complete but spells out West's honor,
      because "low to the Q" names declarer's card rather than the honor it
      finesses against.
  - Open question: options discussed 2026-10-31: a trick name that follows the
    missing honors, such as "then finesse again", which keeps a line complete as
    written but needs the check to learn it; or relaxing spec.md
    #describing-lines' rule that a line works as written, which loses the
    check's exact standard. Claude leans toward the first; the user hasn't
    decided.
- [ ] Lead and follow with the lowest of equal choices {#equal-choices}: AKT8
      opposite 532 for 3 tricks reads "Lead the 5 to the A" where "Cash the A"
      plays the same, and Q7 opposite AJ8642 for 5 tricks "Lead the Q and play
      the 6" where "Run the Q" does.
  - Note: which of declarer's equal cards the search plays shapes the line too,
    and neither fixed choice reads better overall: playing the highest equal
    card instead changed 537 of 4,121 lines or remarks, 236 to shorter lines and
    169 to longer. Letting the describer choose among equal cards line by line
    could take the better of each. The sample came from the SuitPlay
    comparison's tricky holdings, checked 2026-10-31.
  - Note: the candidates' preference (`Preference` in `describe.rs`) also tries
    the lower group of equal cards first, which picks among plays that win in
    exactly the same layouts, such as "Low to the 9, then low to the J" for A9
    opposite JT3 for 2 tricks. Trying the higher group first changed 838 of the
    same 4,121 lines or remarks and no chance; today's order gave the shorter
    line in 302 and the longer in 220 (checked 2026-10-31). The order shapes
    only how lines read, so spec.md leaves it to the code.
  - Note: preferring the lower card among ties, in the candidates' preference,
    was tried and dropped: reordering the candidates changes which plays the
    describer tries at all, and it lost KQ964 opposite A852's safety play. A fix
    could rename a play only among ones whose lines read the same.
- [ ] Find out why playing the highest equal card regroups KT9xxx opposite xxx
      for 5 tricks {#highest-card-regrouping}. Today the line reads "Low to the
      K. If West wins with the A, cash the K. Otherwise, duck a round." Playing
      the highest of declarer's equal cards instead gives "Low to the K. If West
      wins with the A and East plays the Q or the J, cash the K. Otherwise, duck
      a round (if West plays the Q or the J, play the K)."
  - Rationale: the user, 2026-10-31: surprising for this example, and likely
    low-hanging fruit.
  - Note: the trigger, worked out by hand: the holding is KT9432 opposite 765,
    against the A, Q, J, and 8. Once East's 8 falls, North's T, 9, 4, 3, and 2
    are all equal, so the highest-card rule plays the T where today's rule plays
    the 4. The branch where West wins the A and East drops the 8 then moves from
    "cash the K" to the duck. Still unexplained: why the describer finds that
    grouping the cheapest. Plays match across branches by their cards, and
    matching them by their role instead, such as "a low card", may be the fix.
  - Note: to reproduce, drop the `else if !is_touching` branch in
    `Solver::distinct_plays`, which makes the search play the highest equal
    card.
- [ ] Merge stated answers that give the same reply {#merged-answers}: T62
      opposite Q43 for 1 trick reads "duck a round (if East plays the 9, the 8
      or the 7, play the Q; if East plays the 5, play the Q; if East plays the
      J, play the Q)", where one answer naming all five cards would do.
- [ ] Offer "Either" only for lines that read differently: K975 opposite AT86
      for 4 tricks offers "Cash the K, then cash the A" and "Cash the A, then
      cash the K", which differ only in plays the line leaves out.
  - Open question: what should count as reading differently, precisely enough
    for spec.md to state it as the target. The two K975 lines do differ in
    words.
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
- [ ] Give "onside" and "offside" their natural meaning, as spec.md #remarks
      defines them {#onside-naming}. The code places every card by the defender
      who plays second to the first finesse on the usual path. So QT85 opposite
      A742 for 4 tricks gets "Finesse hoping the K is singleton offside", where
      the A drops East's singleton K before the finesses against West, and a
      line that finesses each defender for a different card places both cards by
      the first finesse.
  - Note: a remark beside "too many cases" has no line to say which defender is
    onside, and shortening can change which finesse comes first: AK987 opposite
    52 for 3 tricks went from "hoping the Q or J or T is offside" to "onside".
    Naming the defender would settle both.
- [ ] Give remarks for lines without a finesse the conditions that need one:
      AQ8x opposite K9xx for 4 tricks, whose complete line cashes top cards
      unless someone shows out, says only "Play for the drop", where it once
      said "Finesse hoping the suit splits 3-2, or the J and T are split".
  - Note: conditions about where a card lies, such as "the J and T are split",
    come only with a finesse to set onside; one that fits either way round would
    serve a drop as well.
- [ ] Name the technique correctly when one hand is void {#void-technique}:
      AKT74 opposite a void for 3 tricks gets "Finesse hoping the suit splits
      4-4, plus 7.34% more", though with nothing to lead from in the other hand
      no finesse is possible; the line ducks a round first.
- [ ] Keep a remark's success condition from claiming deals the line loses:
      AQ942 opposite J73 for 5 tricks, which wins 13.57% of the time, reads
      "Repeated finesse hoping the K is onside and the T is singleton or
      doubleton offside, with a small extra chance when the K is singleton or
      doubleton". Five strategies tie, and the remark fits the first, which wins
      when West holds K8x, Kxx, or KT. It loses when West holds K8xx and East
      the singleton T, a layout the condition claims; none of the five wins
      there.
  - Rationale: the user, 2026-10-31: "Remarks should probably not claim lost
    deals."
  - Note: spec.md #remarks says only that a condition may give up a little
    accuracy for simplicity; once this settles, say there which way.
  - Note: the remark follows spec.md #remarks, checked 2026-10-31. Its condition
    misses 6.22% of deals, within the 10% that `MAX_CONDITION_ERROR` in
    `remark.rs` allows: 2.83% where East's singleton T loses, and 3.39% won with
    West's KT, outside the condition. The facts in #remarks have no "exactly
    doubleton", which would fit better.
  - Note: common, checked 2026-10-31 on the SuitPlay comparison's 4,121 tricky
    problems: of 494 remarks stating a success condition, 92 claim deals the
    line loses, 29 of them more than 5% of all deals. 98 opposite AKT65 for 4
    tricks, which wins 66.78%, reads "Finesse hoping the Q or J is onside",
    though the line loses in 9.22% of deals where the Q or J is onside. Wins the
    condition leaves out are mentioned as extras; claimed losses never are.
  - Open question: a tolerance relative to the line's chance, rather than in
    deals, would reject this condition, and the remark would name only the
    technique.
  - Note: the user, 2026-10-31, plans to review remarks against the flashcards
    as they build them up, for practical examples to compare against.
- [ ] Name the defender in an extra chance when the condition names one: 976
      opposite QT for 1 trick reads "Finesse hoping the J is singleton or
      doubleton offside, with a small extra chance when the J is singleton or
      doubleton", which reads as repeating the condition.
  - Note: `extras_words` in `remark.rs` places a short card with either
    defender, never one side; noticed 2026-10-31 in the SuitPlay comparison's
    tricky holdings, where T98 opposite Q7 and its kin read the same way.
- [ ] Leave out a part that the "Otherwise" plays correctly too
      {#otherwise-parts}: AKJ87 opposite 965 for 4 tricks reads "Cash the A",
      then "If West plays the T and East plays a low card, low to the 8, then
      cash the K, then lead low", beside an "Otherwise" of "low to the J" with
      its own two parts.
  - Note: checked by hand, 2026-10-31: in each of the six layouts where West
    plays the T and East a low card, the "Otherwise" and its parts make 4 tricks
    too, so the line can drop the T's part.

---

## Backlog

- [ ] Wire the analyzer into the card generator (`anki/`), whose input file
      holds a hand-typed success %, line, and remarks today.
  - Note: `suit_combinations -` reads one problem per line of standard input, so
    the generator can analyze a whole file in one process.
- [ ] The constraints `flashcards/tasks.md` #suit-combination-constraints queues
      for the cards {#constraints}. CCAnalyser takes most of them: the hand on
      lead, side entries to each hand, each defender's known cards in other
      suits, and each defender's maximum HCP.
  - Note: limited entries make the hand each trick is won in matter, which the
    unlimited-entries model ignores.
- [ ] Decide how to break ties among strategies that reach the target equally
      often {#strategy-tiebreak}. Today the chance of one overtrick decides
      first, so a strategy that makes one overtrick 90% of the time beats one
      that makes three overtricks 85% of the time and otherwise none (spec.md
      #goal).
  - Note: the frontier keeps both kinds of strategy, as spec.md #search says, so
    a different tiebreak changes only which strategy is picked at the end, not
    the search.
- [ ] Explore whether the analyzer should model randomized plays by either side
      {#randomized-plays}. spec.md #model has declarer commit to one strategy
      that the defenders know, so a line that reacts to a defender's card can be
      beaten by any card that steers it wrong. Declarer varying the play, or the
      defenders varying theirs, could change both the best line and its chance.
  - Note: the test case, worked out by hand 2026-10-31: KQT opposite 97 for 2
    tricks reads "Lead the 9 to the K, then low to the Q". After East takes the
    K with the A, cashing the Q hopes the J falls, where finessing the T would
    win whenever West holds the J. Against defenders who know the line, the cash
    is right: holding the A with West holding the J, East would duck the K, so a
    finesse planned for after the A never comes up.
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
- [ ] A command that scores a line the user names {#score-line}: the chance of
      each target, from the start or from a position partway through the play.
  - Open question: how to name a line, whether in the descriptions' own wording,
    such as "low to the Q, then low to the 9", or in a terser notation; and how
    to name a position partway through, such as by the cards each hand played to
    the first trick.
  - Open question: what to play where the named line says nothing: past its end,
    after a defender's card it gives no answer to, or once a card it names is
    gone. A scratch prototype let the solver play its best in all three.
  - Note: the prototype, in `scratch/line_scoring/`, reimplemented `Frontier`'s
    combining outside the crate, since `Frontier::new`, `single`, `merge`, and
    `combined_with` are private to `solver.rs`. Its `compare` produced the
    figures below.
  - Note: the prototype's figures for AQ942 opposite J73, as 4 tricks / 5
    tricks. From the start: the best line, low to the Q, 87.61% / 13.57%; low to
    the 9, then the solver's best, 71.22% / 13.57%. After low to the Q with
    West's 6 and East's 5, over the layouts still possible: low from North
    toward the J 100% / 0%; lead the J and play the 9, 89.13% / 13.04%; low to
    the 9, 89.13% / 13.04%; cash the A, 78.26% / 26.09%.
- [ ] Decide what a line should play after a defender's mistake that the rule in
      spec.md #goal doesn't settle {#passed-up-guarantee}. In AQ942 opposite J73
      for 4 tricks, after low to the Q with West's 6 and East's 5, leading low
      from North toward the J guarantees 4 tricks: play the 7 if East plays the
      K, and the J otherwise. The analyzer's line leads the J from South
      instead.
  - Note: the analyzer's line doesn't guarantee 4 tricks from there. It makes
    them in 89.13% of the layouts still possible, failing when East holds KT85,
    and in exchange makes 5 tricks when West holds K86, which the sure play
    never does (#score-line has the figures).
  - Note: why, checked 2026-10-31 with `scratch/line_scoring`'s `falsecard`:
    East's 5 from KT85 is a mistake. Winning North's Q with the K leaves no way
    to make 4 tricks in that layout, so against best defense the layout is lost
    whatever declarer does after the 6 and 5, and the overtrick tiebreak
    (spec.md #goal) prefers the J. So the analyzer does count on a defender's
    play to the first trick, as the user asked: East winning the Q from KT85.
  - Note: the rule in spec.md #goal for improving on a strategy after a
    defender's mistake doesn't reach this case, since neither continuation beats
    the other in every layout.
  - Open question: whether, after a defender's mistake, a line should play its
    best for the layouts still possible, as a player at the table would, putting
    the target ahead of overtricks. That is a stronger form of the rule in
    spec.md #goal, and it would change which strategy #strategy-tiebreak's
    ranking picks.
  - Rationale: the user, 2026-10-31: the best line here is situational, since
    the defenders might be inexperienced, or might be trying to throw declarer
    off to force a misguess in another suit. The analyzer's line is the right
    one to report for now.
