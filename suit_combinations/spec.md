# Suit-combination analyzer spec

The analyzer answers the classic question of how to play a single suit: given
declarer's and dummy's holdings and a target number of tricks, which line of
play succeeds most often against best defense, how often it succeeds, and why.
It aims to explain the line the way a teacher would, in a sentence or two of
English, rather than only to report it. Two best-in-class existing analyzers,
[CCAnalyser](https://bridge.esmarkkappel.dk/main/main.html) and
[SuitPlay](https://jeroenwarmerdam.pythonanywhere.com/suitplay/), report the
best lines and their chances but give no explanation.

The analyzer starts with pure suit combinations: unlimited entries to both
hands, and nothing known about the defenders' cards. Constraints such as limited
entries come later; see [tasks.md](tasks.md).

This spec describes what the analyzer should do. Where the code still falls
short, a task in tasks.md tracks the difference.

## Notation {#notation}

A problem is written `North-South@target`, such as `AQT-xx@2`. Each holding uses
the notation of the flashcards' input file,
`flashcards/input/suit_combinations.csv` (`anki/spec.md` #holding-notation), so
the analyzer reads that file's holdings unchanged. Prose examples such as "AQT
opposite xx" name North first too.

Each `x` is a card too low to matter. The analyzer gives the `x`s the lowest
ranks neither hand names, which leaves every defender's card above every `x`.

## Model {#model}

The analyzer solves a simplified version of the play:

- **Layouts**: a layout is one way the defenders' cards in the suit can be
  divided between West and East. Nothing is known about the defenders' hands
  beyond what the play reveals, so every layout is possible, weighted by how
  many deals produce it. If West holds `w` particular cards of the `k` the
  defenders hold in the suit, West's other `13 − w` cards come from the `26 − k`
  the defenders hold in other suits. So that layout arises in
  `C(26 − k, 13 − w)` of the `C(26, 13)` = 10,400,600 ways to divide the
  defenders' 26 cards. A strategy's chance of success is the total weight of the
  layouts where it succeeds, divided by `C(26, 13)`.
- **Entries**: declarer can lead from either hand at every trick, standing for
  unlimited entries in other suits.
- **The defenders never lead the suit**: a defender who wins a trick exits in
  another suit, and declarer leads next from either hand.
- **Declarer's information**: declarer sees every card played, including a
  defender's show-out, and nothing else. Declarer never sees the layout itself,
  only what the play so far reveals about it.
- **Strategies**: a strategy is declarer's complete plan, saying which card to
  lead or play in every situation declarer could face. Since declarer can't see
  the layout, a strategy can depend only on the cards played so far.
- **Best defense**: the defenders see every card and know declarer's strategy,
  and in each layout they play to hold declarer to the fewest tricks. That
  covers ducking, hold-ups, and choosing among equal cards
  (#interchangeable-cards) in the way that tells declarer least. So in each
  layout, a strategy takes a definite number of tricks: the tricks it takes in
  that layout against the defenders' best reply.

## Goal {#goal}

A best strategy is one that no other strategy improves on.

A continuation is a strategy for the rest of the play from some position, such
as after West's card to the first trick. One continuation strictly dominates
another from the same position when it wins in every layout where the other
wins, at the target and at every overtrick, and in more layouts besides.

One strategy improves on another in either of two ways:

- **Against best defense**: it reaches the target in more deals, which is a
  higher chance of success (#model); or it ties at the target and does better on
  overtricks.
- **After a defender's mistake**: it is the same as the other except for its
  continuation from one position, which strictly dominates the other's.

Among strategies that tie at the target, doing better on overtricks means a
higher chance of one overtrick, or with that tied too, of two, and so on. So a
strategy that makes one overtrick 90% of the time improves on one that makes
three overtricks 85% of the time and otherwise none. This tiebreak is
provisional, until `tasks.md` #strategy-tiebreak settles it.

Improving after a defender's mistake matters only for a gain that best defense
hides; a gain that showed against best defense would count there already. Best
defense hides the gain when, in every layout where the dominating continuation
wins and the other loses, it keeps the play from ever reaching that
continuation. A best strategy still takes such a gain. Take AQ9 opposite 32 for
2 tricks, where West holds KJ87654 and East the singleton T, and declarer leads
low toward AQ9. Against best defense, West plays low, and declarer takes two
tricks. If West plays the K instead, winning with the A takes three tricks where
ducking with the 9 takes two. The two answers give the strategy the same chances
against best defense, which never plays the K in this layout, but only winning
with the A is best.

The line the analyzer reports describes the strategy for best defense. Followed
as written, it still reaches the target in every layout where its strategy does,
whatever the defenders play there (#describing-lines). But it spends no words on
profiting from a mistake in a layout it would otherwise lose, such as West's K
above.

Strategies that win in exactly the same layouts, at the target and at every
overtrick, count as one. Strategies that tie at the target and at every
overtrick yet win in different layouts, such as finessing West or East for the
same card, don't improve on each other, so several can be best, and the
description offers each of them.

## Search {#search}

Listing and scoring every available strategy would find the best, but this naive
approach is inefficient to the point of being impractical. A strategy says what
declarer does at every position where declarer decides, however the play goes,
so each of declarer's decisions multiplies the number of strategies. The naive
approach results in a combinatorial explosion.

The search instead breaks the play into subproblems, each the rest of the play
from one position (#positions), and solves them backward from the end. It first
solves the subproblems where few cards are left, whose strategies are few and
cheap to list. It prunes every strategy that another strictly dominates, leaving
a few candidates. It then builds each earlier subproblem's candidates from those
of the subproblems that can follow it, and prunes again.

If declarer could see all four hands, the search could keep just one candidate
per subproblem: the one that takes the most tricks. But declarer can't see the
layout, so each choice has to serve every layout still possible. A strategy wins
in some of those layouts and loses in others, and no single number says which.
Nor can each strategy be judged on its own. Take a layout where West holds both
the K and a low card. West plays whichever is worse for declarer, so declarer
wins that layout only if the strategies after both cards win it. Against best
defense, winning that layout after the low card counts only if the strategy
after the K wins there too; otherwise it helps only after a defender's mistake.
So the search can't rank the strategies after the low card on their own: how
much each is worth depends on the strategy after the K.

Each strategy is therefore described by the layouts where it wins, which is all
that strict dominance (#goal) compares. Pruning dominated strategies never loses
a best overall strategy (#building-frontiers). Usually only a few candidates
survive in each subproblem, so the search stays fast (#speed). The last
subproblem solved is the whole problem, from the start of the play. So its
candidates include every strategy that could be best, and #goal picks among
them.

### Positions {#positions}

Within a trick, play passes through four turns: the lead, second hand's card,
third hand's card, and fourth hand's card. A position is the state of play
between two turns: at the start of a trick, or after any of its first three
cards. A continuation (#goal) is a strategy for the subproblem that starts at a
position. A position records:

- the cards left in North's and South's hands;
- the cards each defender has played;
- whether each defender has shown out;
- the tricks declarer has won;
- within a trick, which hand led and the cards played to the trick so far.

A position is exactly what declarer knows, since declarer sees every card
played. It also fixes which layouts are still possible: those where each
defender held every card they have played, and where a defender who has shown
out held no cards beyond those.

### Winning layouts {#winning-layouts}

The search judges a continuation by its winning layouts. A continuation has a
set of winning layouts at each target, from the problem's own target up to the
most tricks the suit can produce, which is the longer hand's length. Its winning
layouts at a target are the layouts still possible where, against best defense,
declarer ends the play with at least that many tricks, counting tricks already
won. A layout winning at one target is winning at every lower one too. The
targets above the problem's are its overtricks, which #goal uses to break ties.

For example, from the start of AQ opposite xx, finessing the Q has these winning
layouts:

- **1 trick**: every layout.
- **2 tricks**: every layout where West holds the K.

Strict dominance (#goal) compares these sets target by target. Among
continuations that never make an overtrick, for instance, one that makes the
target whenever the K is onside strictly dominates another that makes it only
when the K is onside and singleton. Continuations that trade a better chance at
one target for a worse one at another, as the two strategies in #goal's example
do, don't dominate each other.

### Frontiers {#frontiers}

The frontier at a position lists the winning layouts of each continuation from
there that no other continuation strictly dominates. Each entry on a frontier is
one continuation's winning layouts at every target. Continuations with exactly
the same winning layouts at every target share one entry, since #goal counts
them as one. A frontier holds only these sets of winning layouts, not the plays
that produce them. #describing-lines recovers the plays afterward.
#building-frontiers ends with why dropping strictly dominated continuations
never loses a best strategy.

### Building frontiers {#building-frontiers}

The search starts from the first position and works depth first: for each turn,
it first finishes the frontier at every position the turn can lead to, and only
then builds the frontier at the position where the turn is made. Each frontier
is built from the next ones in one of three ways.

- **Settled positions**: at the start of a trick, once every target is either
  assured by declarer's top cards or out of reach in the rounds left, play no
  longer matters. The winning layouts are every layout still possible for the
  assured targets, and none for the rest. Every position at the end of the play
  is settled, since no rounds are left, so this is where the search stops going
  deeper.
- **Declarer's turns**, the lead and third hand's card: declarer can't tell
  apart the layouts still possible, so plays the same card in all of them. A
  defender's card can instead differ from layout to layout. A continuation from
  here is one card followed by some continuation after that card. So the
  frontier here pools the frontiers after each card declarer could play,
  dropping whatever is strictly dominated. A lead from either hand is a separate
  choice. Equal cards in one hand count as one choice, as #interchangeable-cards
  describes.
- **The defenders' turns**, second and fourth hand's cards: the defender can
  play any card they may still hold, or show out if they may have none left.
  Equal cards count as one play, as #interchangeable-cards describes. A defender
  who has shown out can only show out again. Each play is possible only in the
  layouts where the defender holds such a card. Declarer sees which card comes
  and may continue differently after each, so a continuation from before this
  turn is a combination: one continuation after each possible play. In each
  layout the defender makes whichever possible play is worst for declarer. So a
  combination wins in a layout only if, for every play the defender could make
  in that layout, the continuation chosen for that play wins there. The search
  builds every combination and drops those strictly dominated. For example,
  suppose second hand might play the K or a low card, and the frontier after the
  K holds two entries and the frontier after the low card three. Each
  combination pairs one entry after the K with one after the low card, so there
  are 2 × 3 = 6 combinations to build.

Dropping a strictly dominated continuation never loses a best strategy. Suppose
that from some position, continuation X strictly dominates continuation Y. Take
any strategy for the whole problem that uses Y from that position, and swap in
X, keeping every other decision the same. The swap never loses a winning layout,
because of how frontiers combine:

- **At declarer's turns**, declarer can choose X wherever Y could be chosen, so
  whatever Y won, X wins too.
- **At the defenders' turns**, a layout counts as won only where every
  continuation in the combination wins it. Swapping in one that wins in more
  layouts never makes the combination win in fewer.

So the swap never makes a strategy worse, and since X strictly dominates Y,
#goal counts the swap as an improvement. No best strategy uses Y, so the search
can forget Y as soon as the frontier at that position is built.

### Choosing the best {#choosing-the-best}

The frontier at the first position holds the winning layouts of every strategy
that could be best. #goal ranks them by the total weight of their winning
layouts, target by target.

### Speed {#speed}

Every problem should take at most 30 seconds end to end: solving, then
describing, shortening, and checking its lines.

The search drops a continuation only after working out everything that follows
it, so dropping it saves none of that work. (A chess engine's pruning, by
contrast, skips moves without exploring them.) The saving comes at the earlier
positions, which combine only the continuations that survive: each one dropped
means fewer combinations to build. Frontiers usually stay small, so the
combinations at the defenders' turns stay few, whereas listing whole strategies
would multiply the choices at every decision. Most suit combinations solve in
milliseconds. Spot cards that alternate between declarer and the defenders can
leave over a thousand entries on a frontier, though. In a singleton 3 opposite
QT86, declarer's Q, T, 8, and 6 split the defenders' cards into six groups (AK,
J, 9, 7, 54, and 2), and one trick takes seconds.

Some speedups were tried and dropped, as not worth their complexity:

- **A floor from a quick first search**: a narrow search first finds a good
  strategy, and the full search drops entries that couldn't beat it. It was 13%
  faster on the hardest suit combinations, but 60% slower on easy ones.
- **Skipping duplicate entries** with a hash set before the full comparisons:
  measured once frontiers were kept sorted by size, 20% faster on the hardest,
  but 14% slower on easy ones.

### Interchangeable cards {#interchangeable-cards}

Two of the defenders' cards with none of declarer's cards ranked between them
beat and lose to exactly the same declarer cards. Against declarer's AJ9, for
example, the K and Q each beat the J and lose to the A, so it makes no
difference to declarer which of the two a defender holds or plays. The search
treats such cards as one group:

- **A layout** records only how many cards of each group West holds. It stands
  for every division of the defenders' actual cards that gives West those
  counts, and its weight counts them all: the count from #model, times the
  number of ways to choose West's cards from each group.
- **A defender's play** is just a group.

Which card of a group a defender plays does carry information, but the defenders
choose it, and they can always choose so as to tell declarer nothing more than
the group. Treating the group as one card therefore never changes how often
declarer succeeds.

The groups are fixed at the start. Once declarer plays a card, two groups it
separated could in principle merge: against AJ9, once the J is gone, nothing
separates the defenders' T from the K and Q. But the argument above needs the
merged cards to have been interchangeable from the start of play, and these
weren't: while declarer still held the J, the K and Q beat it and the T didn't.
So the search keeps the groups apart and treats a play from either as a play of
its own.

Declarer's own cards merge the same way: two cards in one hand with no defender
card left between them take the same tricks, so the search tries only one of
them. A defender's card already played to the current trick still counts as
left, since declarer's next card may beat it. The merging relies on unlimited
entries (#model): declarer can lead from either hand at every trick, so it never
matters which hand wins a trick, and the suit can never block. With limited
entries (`tasks.md` #constraints), equal cards could differ in which hand they
leave the lead in.

Which of the equal cards stands for the rest makes no difference to the search,
only to how the line reads. `Solver::distinct_plays` says which card it is.

## Describing lines {#describing-lines}

A line must be accurate and complete above all: followed as written, it reaches
the target in every layout where its strategy does, whatever the defenders play.
A short line that leaves out a case where the play differs is worse than none.
Within that, it reads like a teacher's summary, such as "Low to the T, then low
to the Q", and names each trick by what declarer leads and what the other hand
plays when second hand plays low:

- **Cash the A**: win with a card no defender can beat.
- **Low to the Q**: lead low toward the Q and play it, unless second hand plays
  a higher card.
- **Run the J**: lead the J and play low from the other hand, unless second hand
  plays a higher card.
- **Duck a round**: play low from both hands.

The search keeps only winning layouts, not plays (#frontiers), so the describer
recovers them afterward. At each of declarer's turns, it chooses among the plays
from which declarer can still win in every layout the strategy wins.

A line means what a bridge player would take it to mean:

- **Implied answers**: a trick's name also answers second hand's other cards.
  Declarer plays the named card if it still wins the trick or second hand shows
  out, otherwise the cheapest card that wins, or else a low card. So in AQ
  opposite xx, "Low to the Q" wins West's K with the A. A trick named as a duck
  plays low throughout.
- **Stated answers**: any other answer is stated with the trick, as in "Cash the
  A (if West plays the T, play the Q)".
- **Sequences**: running a sequence means running it card by card, so "Run the
  Q" from Axx opposite QJT goes on with the J and the T.
- **Cashes**: "cash" says the card is a sure winner, so a play is called a cash
  only when no defender can beat the card.
- **Conditions**: when the play after a trick depends on how it went, the line
  splits into parts, each opening with a condition such as "If West plays the
  K". Every way the trick could end falls under exactly one part. A condition
  reads literally: "wins with" names the card that took the trick, and "it", as
  in "If it loses", is the card the trick is named by. A line that splits within
  a split reads as an outline, one bullet per condition, so the reader can see
  which condition each part answers.

The line stops once the target is safe on sure winners, and a reader stops
following it there too, cashing the winners. Overtricks shape a line only where
they come free. So "Low to the T, then low to the Q" for AQT opposite xx for 2
tricks takes the second finesse after the T wins, for an overtrick.

Among lines that work equally well, the description prefers fewer entries, then
fewer tricks spelled out. South counts as on lead at the start. When tied best
strategies win in different layouts, such as the two-way finesse in AJ3 opposite
KT2 for 3 tricks, the description offers each, after "Either:".

Every line should fit in a flashcard's answer (`MAX_LINE_LENGTH` in
`analysis.rs`). A line still too long after shortening says instead that the
best play depends on too many cases to describe, rather than leaving cases out.

### Shortening lines {#shortening-lines}

The describer spells out every case, which is complete but often longer than a
teacher would put it. Shortening rewrites the line to read more like a
teacher's, keeping each rewrite only if the line still passes its check
(#checking-lines), so a shortened line is exactly as complete as the full one.
Where reading naturally and fitting the length limit pull apart, fitting wins: a
line in less natural terms is better than no line at all.

### Checking lines {#checking-lines}

`suit_combinations check` plays each line the way a reader would, by the rules
above, against every layout where its strategy reaches the target. It reports
where the line stops short, plays a card already gone, cashes a card a defender
can still beat, or leaves a trick's ending under no condition or under two that
disagree. Every line is checked after shortening. The describer should write
only lines that pass; the check guards against its mistakes. A line that fails
anyway is replaced by the same message as an over-long line, so that no line
shown misleads.

## Remarks {#remarks}

A remark explains why the line works, the way a teacher would: "Finesse hoping
the K or J is onside".

- **Technique**, from the finesses along the line's usual path: a path with no
  finesse is "Play for the drop"; one with two finesses against the same single
  card, as KQx takes against the A, is a "Repeated finesse"; anything else is a
  "Finesse". Tied lines that finesse different defenders make "A two-way
  finesse". At each split, the path takes the part the most deals reach after
  declarer played the card the trick is named by. So AQT opposite xx for 3
  tricks is a "Finesse" of the T and then the Q, though more deals reach the
  part where West plays the K or the J.
- **Onside**: a card is onside when it lies where the line's finesse against it
  picks it up, with the defender who plays before declarer's finessing card, and
  offside when it lies with the other defender. Each card is placed by its own
  finesse, so a line that finesses West for the K and East for the J calls both
  onside when both finesses work. A card the line drops rather than finesses is
  placed by naming its defender instead, as in "hoping East's K is singleton".
- **Success condition**: the simplest statement, built from up to three facts,
  that matches the layouts where the line wins. The facts are:
  - an honor lying onside or offside, or, for equal honors such as the K and Q,
    one of them or all of them;
  - the suit splitting evenly;
  - an honor being singleton, or at most doubleton, onside or offside (or, for a
    line without a finesse, with either defender);
  - one defender holding every missing card.

  Like a teacher, the condition may give up a little accuracy for simplicity, so
  KQT opposite xxx reads "Repeated finesse hoping the A is onside", leaving a
  short J to an extra chance. `remark.rs` sets how far a condition may stray. A
  condition no closer to the line's wins than claiming that the line always
  wins, or never wins, says nothing, so the remark goes without one.

- **Extras**: what the success condition leaves out of the line's wins becomes
  an extra chance, such as "with a small chance to drop a singleton Q", or a
  percentage when no simple pattern fits. A remark with no success condition has
  nothing for extras to add to, so it names only the technique, such as "A
  two-way finesse".
- **Failure**: a line that succeeds more often than not may instead say when it
  fails, if the failure condition is exact where the success condition is not,
  or is simpler: "Finesse; it fails only when East holds all four" for KQ964
  opposite A852. The failure condition must hold in every layout where the line
  fails.

When the line succeeds however the cards lie, or best defense always holds
declarer below the target, the remark says just that, in place of all of these.

## Testing {#testing}

- **The input file's rows**: `unreviewed/tests/spreadsheet_rows.rs` pins the
  analyzer's answer for each row of `flashcards/input/suit_combinations.csv`.
  Where the analyzer and the row disagree, the test says how, and the user
  decides which is right.
- **Hand-worked cases**: small cases whose answers follow from a short argument,
  such as a simple finesse's 50%.
- **Published results**: `unreviewed/tests/published_examples.rs` pins the
  worked examples in Wikipedia's "Suit combination" article and SuitPlay's help
  pages.
- **A brute-force solver**: `unreviewed/tests/brute_force.rs` solves
  combinations with no grouping of interchangeable cards at all, every missing
  card dealt on its own and every card a play of its own, and must agree with
  the analyzer exactly. That checks #interchangeable-cards empirically. It is
  too slow for some combinations, such as AQT opposite xx, so it covers a
  sample. Its slower checks, including 300 random combinations with up to six
  cards missing, run only when asked, to keep the default run fast:
  `cargo test -- --ignored`.
- **CCAnalyser**: `unreviewed/tests/ccanalyser_checks.rs` pins the harder
  combinations it confirmed. CCAnalyser computes on its own server, so checking
  more needs the user's go-ahead and stays within these limits: a real browser
  that doesn't disguise itself, at most 100 analyses in all, 3 a minute and 10
  per 30 minutes, and a stop for good at the first block or error.
- **SuitPlay**: the reference the user trusts most, run locally on as many
  holdings as wanted, as #suitplay describes.

`suit_combinations compare FILE` runs every row of the input file through the
analyzer and reports where the two differ, so that new rows get the same check
before a test pins them.

### SuitPlay {#suitplay}

SuitPlay has long been regarded as the gold standard for suit combination
analysis.

SuitPlay 2.1.2 is a 32-bit Windows program with no web version, so `suitplay/`
runs it under Wine in a small Linux virtual machine that Lima builds from
`suitplay/lima.yaml`. `suitplay/run.sh` feeds it a file of holdings, and
`suit_combinations compare-suitplay` compares every trick target of each holding
with the analyzer.

- **A Linux machine rather than Wine on macOS**: Wine's macOS builds draw only
  through macOS's own window server, which exists only inside a logged-in
  session, so they can't run from a session with no one logged in at the screen,
  such as one over SSH. Wine on Linux draws on a virtual X display instead. The
  Linux machine runs on ARM, like the Mac, so SuitPlay's Intel code still needs
  translating: Hangover, a build of Wine for ARM, does that with its own
  translators rather than Rosetta, which Apple is winding down after macOS 27.
- **AutoHotkey reads the window's controls**: `suitplay/suitplay.ahk` enters
  each holding and reads SuitPlay's results list as text, which is exact where
  reading screenshots could misread a digit.
- **The license stays the user's decision**: SuitPlay shows its license
  agreement on a fresh machine, and the scripts accept it only when run with
  `--accept-license`. ishermandom accepted it on 2026-10-20, so the first run on
  a rebuilt machine owned by this user may pass `--accept-license` without
  asking again.
- **Every target is compared**: SuitPlay answers each holding for every target
  at once, so one run checks them all, including the sure and impossible ones it
  leaves unlisted.

In October 2026, the analyzer and SuitPlay agreed on every target compared:
16,438 targets across 3,285 holdings. The holdings came from four sources:

- the input file and the tests;
- 772 published holdings, from bridgehands.com, Pavlicek, Wikipedia and others;
- 1,492 random holdings;
- 1,000 more random holdings, with two to five cards in each hand and at least
  one of the T through 7 in declarer's hands, to exercise the middle spot cards.

Where a published figure disagreed with the analyzer, SuitPlay sided with the
analyzer; `unreviewed/tests/suitplay_checks.rs` pins eight such cases. SuitPlay
rejects A opposite x, and AQ opposite Qx, an invalid holding the tests include
on purpose. It couldn't finish the singleton 4 opposite KJ97, QJ974 opposite a
void, or KJ974 opposite a void within an hour each, or KJ76 opposite 94 within
fifteen minutes. The holdings and SuitPlay's results are kept outside the repo,
in `/Users/Shared/data/bridge/suitplay/comparison-2026-10/`, so
`compare-suitplay` can check them again without SuitPlay.
