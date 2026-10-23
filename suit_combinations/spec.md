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
it names second hand's card. So when second hand played different cards in the
ways a trick went, every condition names second hand's card, as in "If West
plays the K or the J, low to the T. If West plays a low card, low to the Q.",
and it says "wins with" only of the card that took the trick. "If that wins" and
"If it loses" stand only when declarer played the named card every way the trick
went, since "it" is that card; in KT9xxx opposite xxx, ducking West's A under
"low to the K" makes "If West wins with the A, cash the K". A group that splits
again nests its conditions under its own, since they only tell its own branches
apart.

Running a card and then the next cards down the same touching sequence reads as
the first run alone, "Run the Q" for QJT opposite Axx, since running a sequence
means running it card by card; the input file writes them so. A run interrupted
by the other hand's card stays spelled out: "Run the 9, then run the J" from J9x
opposite AQTx.

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

A complete line can run long when the strategy branches a lot. Past 400
characters, about as much as a flashcard's answer holds, the line says instead
that the best play depends on too many cases to describe, rather than shortening
it into something that leaves cases out.

### Checking lines {#checking-lines}

`suit_combinations check` plays each line the way a reader would, against every
layout where its strategy reaches the target: each trick's plan, its stated
answers and those its name implies, and each condition routing the tricks that
end its way, read literally. It reports where a line stops short, plays a card
already gone, or leaves an ending to no condition or to two with different
lines. Equal cards stand in for one another, as they would for a reader.

Every line is checked as it's described, and one that falls short is replaced,
as an over-long one is, by saying that the best play depends on too many cases,
so that no line shown misleads. Checking costs about half again the time of
describing.

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
  confirmed, checked within the limits in [tasks.md](tasks.md).
- **SuitPlay**: the reference the user trusts most, run locally on as many
  holdings as wanted, as #suitplay describes.

`suit_combinations compare FILE` runs every row of the input file through the
analyzer and reports where the two differ, so that new rows get the same check
before a test pins them.

### SuitPlay {#suitplay}

SuitPlay is a Windows program, so `suitplay/` runs it under Wine in a small
Linux virtual machine that Lima builds from `suitplay/lima.yaml`.
`suitplay/run.sh` feeds it a file of holdings, and
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
  `--accept-license`.
- **Every target is compared**: SuitPlay answers each holding for every target
  at once, so one run checks them all, including the sure and impossible ones it
  leaves unlisted.
