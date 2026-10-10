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

## Testing {#testing}

- **The input file's rows**: `tests/spreadsheet_rows.rs` pins the analyzer's
  answer for each row of `flashcards/input/suit_combinations.csv`. Where the
  analyzer and the row disagree, the test says how, and the user decides which
  is right.
- **Hand-worked cases**: small cases whose answers follow from a short argument,
  such as a simple finesse's 50%.
- **CCAnalyser**: a sample of combinations checked against it, within the limits
  in [tasks.md](tasks.md).
