# Suit-combination analyzer spec

The analyzer answers the classic question of how to play a single suit: given
declarer's two holdings and a target number of tricks, which line of play
succeeds most often against best defense, how often it succeeds, and why. It
aims to explain the line the way a teacher would, in a sentence or two of
English, rather than only report it. The user's reference is CCAnalyser
(https://bridge.esmarkkappel.dk/main/main.html), which reports the best lines
and their chances but no explanation.

The analyzer starts with pure suit combinations: unlimited entries to both
hands, and nothing known about the defenders' cards. Constraints such as limited
entries come later; see [tasks.md](tasks.md).

## Notation {#notation}

A problem is written `North-South@target`, such as `AQT-xx@2`. Each holding uses
the notation of the flashcards' input file,
`flashcards/input/suit_combinations.csv` (`anki/spec.md` #holding-notation), so
the analyzer reads that file's holdings unchanged. North is the hand shown on
top of a diagram, and South the one below it. Prose examples such as "AQT
opposite xx" name North first too.

Each `x` is a card too low to matter. The analyzer gives the `x`s the lowest
ranks neither hand names, which leaves every defender's card above every `x`.

## Model {#model}

- **Layouts**: every way the missing cards can divide between West and East is
  possible, weighted by how many deals produce it, with no other information
  about the defenders' hands. A division with West holding `w` of the `k`
  missing cards arises in `C(26 − k, 13 − w)` of the `C(26, 13)` deals.
- **Entries**: declarer can lead from either hand at every trick, standing for
  unlimited entries in other suits.
- **The defenders never lead the suit**: a defender who wins a trick exits in
  another suit, and declarer leads next from either hand.
- **Best defense**: the defenders see every card and know declarer's strategy,
  and in each layout they play to hold declarer to the fewest tricks. That
  covers ducking, hold-ups, and choosing between cards of equal rank in the way
  that tells declarer least.
- **Declarer's information**: declarer sees every card played, including a
  defender's show-out, and nothing else.

## Goal {#goal}

The best strategy reaches the target in the most deals. Among strategies that
tie, the best makes the most overtricks, comparing the chance of one extra trick
first, then of two, and so on. Strategies that win in exactly the same layouts
count as one. Strategies that tie in every respect yet win in different layouts,
such as finessing West or East for the same card, are all best, and the
description offers each of them.

## Search {#search}

A strategy's result is, for each target from the problem's up to the longer
hand's length, the set of layouts where the strategy reaches it. The search
keeps every result that no other strategy's result contains at every target.

- **Declarer's turn**: declarer makes one choice for every layout still
  possible, so the results gather those of each choice.
- **A defender's turn**: the defenders choose separately in each layout, so a
  strategy succeeds in a layout only if it succeeds after every play that
  defender could make there. Declarer may plan differently after each play, so
  combining one result for each play, in every combination, covers every
  strategy.
- **Memo**: the position at the start of each trick determines everything after
  it, so each position is solved once.
- **Settled positions**: a position needs no search once every target is either
  assured by declarer's top cards or out of reach in the rounds left.

The combinations at a defender's turn can multiply quickly; keeping only the
results no other contains holds them down. Most combinations solve in
milliseconds, but many interleaved spot cards can leave over a thousand results
that no other contains, as for one trick from 3 opposite QT86, which takes
seconds. Each result therefore carries a cheap signature, its size and a folded
word of its first set, that rules out most containment tests before the full
one, and each frontier stays sorted by size: a result can only be contained in
one at least as large, so a new result is checked against the results at least
as large for whether it adds anything, and against the smaller ones for what it
replaces.

Some speedups were tried and dropped, as not worth their complexity:

- **A floor from a quick first search**, dropping results that couldn't beat a
  strategy a narrow search found: 13% faster on the hardest combinations, but
  60% slower on easy ones.
- **Skipping duplicate results** with a hash set before the containment tests:
  20% faster on the hardest, 14% slower on easy ones, once frontiers were
  sorted.

### Interchangeable cards {#interchangeable-cards}

Two of the defenders' cards with no declarer card between them beat and lose to
exactly the same declarer cards, so the search treats them as one group: a
layout records only how many of each group West holds, and a defender's play is
just a group. Which card of a group a defender plays does carry information, but
the defenders choose it, and they can always choose so as to tell declarer
nothing more than the group. Treating the group as one card therefore never
changes how often declarer succeeds.

The groups are fixed at the start. Groups that a played declarer card no longer
separates could merge mid-play, but the argument above needs the merged cards to
be interchangeable in every layout from the start, which such groups aren't, so
the search keeps them apart and treats a play from either as its own.

Declarer's own cards merge the same way: cards in one hand with no defender card
left between them take the same tricks. The search tries one of them, the top of
the lowest run of cards that touch with nothing at all left between them. Within
a run every card is the same in every respect, and starting from the lowest run
keeps the higher cards, which may win the trick in the other hand's stead, for
later. A defender's card already played to the current trick still counts as
left, since declarer's next card may beat it.

## Describing lines {#describing-lines}

A line must be accurate and complete above all: followed as written, it reaches
the target in every layout where its strategy does, whatever the defenders play.
A short line that leaves out a case where the play differs is worse than none.
Within that, it reads like a teacher's summary, such as "Low to the T, then low
to the Q", and names each trick by what declarer leads and what the other hand
plays when second hand plays low:

- **Cash the A**: win with a card no defender can beat.
- **Low to the Q**: lead low toward the Q and play it.
- **Run the J**: lead the J and play low from the other hand.
- **Duck a round**: play low from both hands.

"Second hand plays low" means its lowest card below the card declarer means to
win the trick with, among the cards it might play where the line can still
succeed; declarer's answer to any other card changes nothing. In QT85 opposite
A742 for 4 tricks, which needs East's K to be singleton, East's low cards don't
count, and the first trick reads "Cash the A" rather than naming a low card no
winning layout holds. When second hand has no such card, as when West holds only
the A and Q against a lead of the 9, the play still matches a sibling branch's
"run the 9" by its plan; on its own it ranks below a play named by the card it
really plays, here covering with the K.

The line answers every other card second hand might play where it can still
succeed, and the trick's name implies most answers:

- the named card, while it still wins the trick, and over a show-out;
- otherwise the cheapest card that wins the trick;
- otherwise a low card.

A trick named as ducked plays low throughout, so it never shares a play with a
trick that isn't. An answer the name doesn't imply is stated with the trick:
"Cash the A (if West plays the J, play the Q)". Each answer is recorded as an
instruction, such as "the cheapest card that wins" or "play low", rather than as
a particular card, so branches whose cheapest winning card differs can still
share a play. Playing the named card over a show-out, when that works, means the
card declarer plays is the card the line names: AQJ opposite xx reads "Low to
the Q", where answering West's show-out with the A would go on to "run the Q",
naming the Q twice.

After each trick, the next is joined with "then" when one play suits every way
the trick might have gone; otherwise the line splits into groups that share a
play. A play matches across those branches by its cards rather than its name, so
"low to the Q" still matches once the K has gone and the Q has become a winner;
the description then uses the name that says more.

A condition reads literally: it holds after whatever second hand played unless
it names second hand's card. So when second hand's card differs between the
branches a split covers, every condition names second hand's card, as in "If
West plays the K or the J, low to the T", and a condition uses "wins with" only
for the card that took the trick. "If that wins" and "If it loses" appear only
when declarer played the named card in every branch, since "it" refers to that
card. In KT9xxx opposite xxx, for example, the trick is named "low to the K",
but when West rises with the A, North plays low and keeps the K, so the
condition reads "If West wins with the A, cash the K". When a group splits
again, its conditions nest under the group's own condition, since they tell
apart only that group's branches.

Running a card and then the next cards down the same sequence reads as the first
run alone, "Run the Q" for Axx opposite QJT, since running a sequence means
running it card by card; the input file writes such lines this way too. A card
in the other hand between them breaks the sequence, so each run stays spelled
out: "Run the 9, then run the J" from AQTx opposite J9x.

The line stops once its target is safe on sure winners, and a reader stops
following it there too, cashing the winners. Overtricks shape it only where they
come free: a branch whose target is already safe goes along with the other
branches' play when that play keeps its target safe, which is how "Low to the T,
then low to the Q" keeps its second finesse after the T wins.

Among lines that work equally well, the description prefers:

1. **Fewer entries**: leading from the hand that just won the trick, with South
   on lead at the start. That picks "Run the 9, then run the J" from AQTx
   opposite J9x, which stays in South, and "Cash the K, then run the J" from Axx
   opposite KJT.
2. **Fewer tricks spelled out.**
3. **The lower card first**, so the deeper finesse comes first, as in "Low to
   the T, then low to the Q". Among equal cards in one hand, the lower sequence
   comes first, and within a sequence the top card leads. A card played under a
   winner is always the lowest of its equals, keeping the others.

When tied best strategies win in different layouts, such as a two-way finesse,
the description offers each: "Either:" and one line per strategy.

### Long lines

A line that splits within a split reads as an outline instead of run-on
sentences, one bullet per condition, since a sentence can't show which condition
each part answers. Each way the trick could have ended must fall under exactly
one part's condition; where merging branches would make their later conditions
overlap, the describer splits them earlier instead, while they can still be told
apart.

A complete line can run long when the strategy branches a lot, even once
shortened as #shortening-lines describes. Past 400 characters, about as much as
a flashcard's answer holds, the line says instead that the best play depends on
too many cases to describe, rather than cutting it into something that leaves
cases out.

### Shortening lines {#shortening-lines}

The describer spells out every case, which is complete but often longer than a
teacher would put it. A teacher states the unusual cases and lets "Otherwise"
cover the rest, as in this line for AQT opposite xx for 3 tricks: "Low to the T.
If West plays the K or the J, low to the T. Otherwise, low to the Q." The line
is shortened by rewrites like that one, and each rewrite stands only if the line
still passes its check (#checking-lines). A shortened line is therefore exactly
as complete as the full one; shortening never trades accuracy for brevity.

- **Unneeded answers**: an answer stated with a trick is removed when the reader
  reaches the target without it.
- **"Otherwise"**: one part of a split takes "Otherwise" as its condition and
  moves last. Then each other part is removed if the "Otherwise" line also
  reaches the target in that part's branches, and a split left with only
  "Otherwise" becomes that part's line.

The part that says "Otherwise" is the usual case, the one a teacher would leave
unstated. The usual case is the part holding the most deals in which declarer
played the card the trick is named by, as declarer does when second hand plays
low. Among parts as usual as one another, the one with the longest condition
takes "Otherwise", saving the most words. In AQxxx opposite J9xx for 5 tricks,
once the Q holds, the usual case reads "Otherwise, cash the A", dropping West's
doubleton K. Making "run the J" the "Otherwise" instead would save a part, but
it repeats the finesse against a K the A would drop. The remark (#remarks),
which follows the line's usual path, would then call the play a repeated
finesse.

In two cases the describer sets the usual case aside and removes the most parts
instead: in each split, it tries the six most usual parts as "Otherwise", and
keeps the one that removes the most other parts, the more usual of any that tie.
The two cases are:

- **Past the limit**: the usual case leaves the whole description, with tied
  lines counted together, past the length limit. A line in less usual terms is
  better than no line at all. Of 2,652 sampled lines too long before shortening,
  the usual case alone brought 810 within the limit, and removing the most parts
  brought 1,409.
- **Two parts fewer**: removing the most parts leaves the whole description at
  least two parts shorter than the usual case does. In JT97 opposite K83 for 3
  tricks, it leaves "If East plays the Q, ... Otherwise, run the J, then low to
  the T", whereas the usual case splits four ways, two of them reading the same.
  A single part fewer reads better about as often as it reads worse. In T53
  opposite AKQ94 for 4 tricks, for example, the usual case names West's
  show-out, whereas removing the most parts would name every card West might
  follow with instead.

The describer judges both cases on the whole description rather than split by
split, because the part chosen as "Otherwise" in one split can push the
branching to a later trick, where the line splits into more parts than before.

### Checking lines {#checking-lines}

`suit_combinations check` plays each line the way a reader would, against every
layout where its strategy reaches the target. In each trick it follows the plan,
the answers the line states, and the answers the trick's name implies. After
each trick it reads every condition literally and follows the part whose
condition matches how the trick ended; "Otherwise" takes every ending that no
other condition in its split matches. It reports where a line stops short, plays
a card already gone, or routes a trick's ending to no condition, or to two
conditions whose lines differ. Equal cards stand in for the low cards a line
leaves unnamed, as they would for a reader, but a card the line names must be
that card.

It also reports a "cash" of a card a defender can still beat. Every other name
says only what declarer plays, which stays true whatever the defenders hold, but
"cash" also says the card is a sure winner. When several branches share a play,
its name comes from the branch where that name explains the play best, and a
cash explains least, so a shared play is called a cash only when it is a cash in
every branch. Shortening merges parts into the one that says "Otherwise", whose
play names then cover the merged parts' branches too, so the check holds a
shortened line to the same rule.

Every line is checked after shortening. A line that fails the check is replaced
by the same message as an over-long line, that the best play depends on too many
cases, so that no line shown misleads.

## Remarks {#remarks}

A remark explains why the line works, the way a teacher would: "Finesse hoping
the K or J is onside".

- **Technique**, from the finesses along the line's usual path: a path with no
  finesse is "Play for the drop"; one with two finesses against the same single
  card, as KQx takes against the A, is a "Repeated finesse"; anything else is a
  "Finesse". Tied lines that finesse different defenders make "A two-way
  finesse". At each split, the path takes the part the most deals reach after
  declarer played the card the trick is named by, as the usual case does
  (#shortening-lines). So AQT opposite xx for 3 tricks is a "Finesse" of the T
  and then the Q, though more deals reach the part where West plays the K or the
  J.
- **Onside**: a card is onside when it lies with the defender who plays before
  declarer's finessing card in the line's first finesse.
- **Success condition**: the simplest statement, built from up to three facts,
  that matches the layouts where the line wins. The facts are:
  - an honor lying onside or offside, or, for equal honors such as the K and Q,
    one of them or all of them;
  - the suit splitting evenly;
  - an honor being singleton, or at most doubleton, onside or offside (or, for a
    line without a finesse, with either defender);
  - one defender holding every missing card.

  A success condition may miss by up to 10% of deals; a simpler one is preferred
  when it misses by at most 5% more, which keeps "Repeated finesse hoping the A
  is onside" for KQT opposite xxx rather than adding a clause for a short J.

  A success condition that holds in every layout, or in none, says nothing and
  is never chosen. Nor is one that misses as many deals as the claim that the
  line always wins, or the claim that it never wins, would miss. For AKT9
  opposite xx for 4 tricks, a line that wins 5.17% of the time, the condition
  "West holds all seven" holds in almost none of the line's wins, so the remark
  is just "Finesse".

- **Extras**: what the success condition misses becomes an extra chance, such as
  "with a small chance to drop a singleton Q", or a percentage when no simple
  pattern fits; above 5% of deals it is no longer called small. A remark with no
  success condition has nothing for extras to add to, so it names only the
  technique, such as "A two-way finesse".
- **Failure**: a line that succeeds more often than not may instead say when it
  fails, if the failure condition is exact where the success condition is not,
  or is simpler: "Finesse; it fails only when East holds all four" for KQ964
  opposite A852. The failure condition must hold in every layout where the line
  fails.

When the line succeeds however the cards lie, or best defense always holds
declarer below the target, the remark says just that, in place of all of these.

## Testing {#testing}

- **The input file's rows**: `tests/spreadsheet_rows.rs` pins the analyzer's
  answer for each row of `flashcards/input/suit_combinations.csv`. Where the
  analyzer and the row disagree, the test says how, and the user decides which
  is right.
- **Hand-worked cases**: small cases whose answers follow from a short argument,
  such as a simple finesse's 50%.
- **Published results**: `tests/published_examples.rs` pins the worked examples
  in Wikipedia's "Suit combination" article and SuitPlay's help pages.
- **A brute-force solver**: `tests/brute_force.rs` solves combinations with no
  grouping of interchangeable cards at all, every missing card dealt on its own
  and every card a play of its own, and must agree with the analyzer exactly.
  That checks #interchangeable-cards empirically. It is too slow for some
  combinations, such as AQT opposite xx, so it covers a sample. Its slower
  checks, including 300 random combinations with up to six cards missing, run
  only when asked, to keep the default run fast: `cargo test -- --ignored`.
- **CCAnalyser**: `tests/ccanalyser_checks.rs` pins the harder combinations it
  confirmed. CCAnalyser computes on its own server, so checking more needs the
  user's go-ahead and stays within these limits: a real browser that doesn't
  disguise itself, at most 100 analyses in all, 3 a minute and 10 per 30
  minutes, and a stop for good at the first block or error.
- **SuitPlay**: the reference the user trusts most, run locally on as many
  holdings as wanted, as #suitplay describes.

`suit_combinations compare FILE` runs every row of the input file through the
analyzer and reports where the two differ, so that new rows get the same check
before a test pins them.

### SuitPlay {#suitplay}

The user treats SuitPlay as the gold standard. Newer analyzers that run locally,
such as jdh8/suit-combination and Quaestio, didn't seem reliable enough to
interest them.

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
  `--accept-license`. The user accepted it on 2026-10-20, so the first run on a
  rebuilt machine may pass `--accept-license` without asking again.
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
analyzer; `tests/suitplay_checks.rs` pins eight such cases. SuitPlay rejects A
opposite x and AQ opposite Qx. It couldn't finish 4 opposite KJ97, QJ974
opposite a void, or KJ974 opposite a void within an hour each, or KJ76 opposite
94 within fifteen minutes.
