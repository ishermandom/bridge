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
results no other contains holds them down, and suit combinations stay small
enough that the search runs in milliseconds.

### Interchangeable cards {#interchangeable-cards}

Two of the defenders' cards with no declarer card between them beat and lose to
exactly the same declarer cards, so the search treats them as one group: a
layout records only how many of each group West holds, and a defender's play is
just a group. Which card of a group a defender plays does carry information, but
the defenders choose it, and they can always choose so as to tell declarer
nothing more than the group. Treating the group as one card therefore never
changes how often declarer succeeds.

Declarer's own cards merge the same way: cards in one hand with no defender card
left between them take the same tricks. The search tries one of them, the top of
the lowest run of cards that touch with nothing at all left between them. Within
a run every card is the same in every respect, and starting from the lowest run
keeps the higher cards, which may win the trick in the other hand's stead, for
later. A defender's card already played to the current trick still counts as
left, since declarer's next card may beat it.

## Describing lines {#describing-lines}

The description reads like a teacher's summary of the line, such as "Low to the
T, then low to the Q", rather than a full strategy tree. It follows one main
line and names each trick by what declarer leads and what the other hand plays
when second hand plays low:

- **Cash the A**: win with a card no defender can beat.
- **Low to the Q**: lead low toward the Q and play it.
- **Run the J**: lead the J and play low from the other hand.
- **Duck a round**: play low from both hands.

"Second hand plays low" means its lowest card below the card declarer means to
win the trick with. When second hand has no such card, as when West holds only
the A and Q against a lead of the 9, declarer's reply stays free; the play is
still "run the 9", and declarer covers. The line also follows second hand
showing out, since a show-out tells declarer where the rest of the suit lies.

After each trick, the next is joined with "then" when one play suits every way
the trick might have gone; otherwise the line splits, first on whether the trick
won or lost, then into groups that share a play. A play matches across those
branches by its cards rather than its name, so "low to the Q" still matches once
the K has gone and the Q has become a winner; the description then uses the name
that says more.

Running a card and then the next cards down the same touching sequence reads as
the first run alone, "Run the Q" for QJT opposite Axx, since running a sequence
means running it card by card; the input file writes them so. A run interrupted
by the other hand's card stays spelled out: "Run the 9, then run the J" from J9x
opposite AQTx.

The line stops once its target is safe on sure winners. Overtricks shape it only
where they come free: a branch whose target is already safe goes along with the
other branches' play when that play suits it, which is how "Low to the T, then
low to the Q" keeps its second finesse after the T wins.

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

## Remarks {#remarks}

A remark explains why the line works, the way a teacher would: "Finesse hoping
the K or J is onside".

- **Technique**, from the finesses along the line's likeliest path: none is
  "Play for the drop"; two against the same single card, as KQx takes against
  the A, is a "Repeated finesse"; anything else is a "Finesse". Tied lines that
  finesse different defenders make "A two-way finesse".
- **Onside** means the defender who plays before declarer's finessing card in
  the line's first finesse.
- **Condition**: the simplest statement, built from up to three facts, that
  matches the layouts where the line wins. The facts are:
  - an honor lying onside, or one or all of a run of equal honors;
  - the suit splitting evenly;
  - an honor being singleton, or at most doubleton, onside or offside (or, for a
    line without a finesse, with either defender);
  - one defender holding every missing card.

  A condition may miss by up to 10% of deals; a simpler one is preferred when it
  misses by at most 5% more, which keeps "Repeated finesse hoping the A is
  onside" for KQ10 opposite xxx rather than adding a clause for a short J.

- **Extras**: what the condition misses becomes an extra chance, such as "with a
  small chance to drop a singleton Q", or a percentage when no simple pattern
  fits; above 5% of deals it is no longer called small.

A line that succeeds in every layout says so instead.

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
  combinations, such as AQ10 opposite xx, so it covers a sample, plus 300 random
  combinations with up to six cards missing in a test that runs only when asked:
  `cargo test -- --ignored`.
- **CCAnalyser**: a sample of combinations checked against it, within the limits
  in [tasks.md](tasks.md).

`suit_combinations compare FILE` runs every row of the input file through the
analyzer and reports where the two differ, so that new rows get the same check
before a test pins them.
