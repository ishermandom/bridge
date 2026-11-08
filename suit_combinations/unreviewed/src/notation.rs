// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Parsing a suit combination problem from its notation, such as `AQT-xx@2`.
//!
//! A holding uses the notation of `anki/spec.md` #holding-notation: cards high
//! to low, `T` or `10` for the ten, `x` for a small card, and `-`, `v`,
//! `void`, or `(void)` for a void. A problem joins North's and South's
//! holdings with `-` and appends `@` and the number of tricks wanted; the
//! first `-` always separates the hands, so `AKQ--` gives South a void.

use std::fmt;

use crate::cards::{Rank, RankSet, SUIT_SIZE, rank_for_symbol, rank_symbol};

/// Why some notation couldn't be parsed, with the offending text.
#[derive(Debug, PartialEq, Eq)]
pub struct NotationError(String);

impl fmt::Display for NotationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for NotationError {}

/// One hand's holding as written: its named cards and how many small ones.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Holding {
    /// The cards the notation names by rank.
    pub named: RankSet,
    /// How many `x` cards the notation lists.
    pub small_count: u8,
}

impl Holding {
    /// How many cards the holding has.
    pub fn len(self) -> u8 {
        self.named.len() + self.small_count
    }

    /// Whether the holding is a void.
    pub fn is_empty(self) -> bool {
        self.len() == 0
    }
}

impl fmt::Display for Holding {
    /// The canonical notation, such as `AQTx` or `(void)`.
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.is_empty() {
            return formatter.write_str("(void)");
        }
        for rank in self.named.descending() {
            write!(formatter, "{}", rank_symbol(rank))?;
        }
        for _ in 0..self.small_count {
            formatter.write_str("x")?;
        }
        Ok(())
    }
}

/// Every spelling of a void, once spaces are removed.
const VOID_SPELLINGS: [&str; 5] = ["", "-", "v", "void", "(void)"];

/// Parse one hand's holding, such as `AQ10x`.
pub fn parse_holding(text: &str) -> Result<Holding, NotationError> {
    // Spacing is cosmetic, so it never distinguishes two holdings.
    let compact: String = text.split_whitespace().collect();
    if VOID_SPELLINGS.contains(&compact.as_str()) {
        return Ok(Holding {
            named: RankSet::EMPTY,
            small_count: 0,
        });
    }

    let mut named = RankSet::EMPTY;
    let mut small_count = 0;
    // The rank of the previous named card, to check the high-to-low order.
    let mut previous: Option<Rank> = None;
    for symbol in compact.replace("10", "T").chars() {
        if symbol == 'x' {
            small_count += 1;
            continue;
        }
        let rank = rank_for_symbol(symbol).ok_or_else(|| {
            NotationError(format!(
                "unknown card {symbol:?} in holding {text:?}; cards are \
                 A K Q J T 9-2 (or 10 for T), and x for a small card"
            ))
        })?;
        let is_in_order = previous.is_none_or(|higher| rank < higher);
        if small_count > 0 || !is_in_order {
            return Err(NotationError(format!(
                "{symbol} is out of place in holding {text:?}; list cards \
                 high to low, naming each at most once, small cards last"
            )));
        }
        named = named.with(rank);
        previous = Some(rank);
    }

    let holding = Holding { named, small_count };
    if holding.len() > SUIT_SIZE {
        return Err(NotationError(format!(
            "holding {text:?} has {} cards; a suit has only {SUIT_SIZE}",
            holding.len()
        )));
    }
    Ok(holding)
}

/// Declarer's two holdings, with every small card assigned a concrete rank.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Combination {
    /// North's holding as written.
    pub north_holding: Holding,
    /// South's holding as written.
    pub south_holding: Holding,
    /// North's cards, with each `x` given its concrete rank.
    pub north: RankSet,
    /// South's cards, with each `x` given its concrete rank.
    pub south: RankSet,
}

impl Combination {
    /// The combination of two holdings, giving the small cards the lowest
    /// ranks that neither hand names.
    ///
    /// Each `x` stands for a card too low to matter, so giving them all the
    /// lowest free ranks leaves every defender's card above every `x`.
    pub fn new(
        north_holding: Holding,
        south_holding: Holding,
    ) -> Result<Combination, NotationError> {
        let shared = north_holding.named.intersection(south_holding.named);
        if let Some(rank) = shared.highest() {
            return Err(NotationError(format!(
                "both hands hold the {} in {north_holding}-{south_holding}",
                rank_symbol(rank)
            )));
        }
        let card_count = north_holding.len() + south_holding.len();
        if card_count > SUIT_SIZE {
            return Err(NotationError(format!(
                "{north_holding}-{south_holding} has {card_count} cards; a \
                 suit has only {SUIT_SIZE}"
            )));
        }

        let named = north_holding.named.union(south_holding.named);
        let mut free_ranks =
            (0..SUIT_SIZE).filter(|&rank| !named.contains(rank));
        // The hand with the lower named cards takes the lower small cards, so
        // that each hand's small cards stay below its named ones wherever
        // that's possible at all. A hand with no named card has none to stay
        // below, so it goes last.
        let lowest_named =
            |holding: Holding| holding.named.lowest().unwrap_or(SUIT_SIZE);
        let north_first =
            lowest_named(north_holding) <= lowest_named(south_holding);
        let mut north = north_holding.named;
        let mut south = south_holding.named;
        let order = if north_first {
            [(north_holding, &mut north), (south_holding, &mut south)]
        } else {
            [(south_holding, &mut south), (north_holding, &mut north)]
        };
        for (holding, cards) in order {
            for _ in 0..holding.small_count {
                // With at most 13 cards in all, a free rank is left for each
                // `x`.
                let rank = free_ranks.next().expect("a free rank");
                if holding.named.lowest().is_some_and(|lowest| rank > lowest) {
                    return Err(NotationError(format!(
                        "{north_holding}-{south_holding} leaves no rank low \
                         enough for each x in {holding}"
                    )));
                }
                *cards = cards.with(rank);
            }
        }
        Ok(Combination {
            north_holding,
            south_holding,
            north,
            south,
        })
    }

    /// How many cards the longer hand holds: the most tricks the suit can win.
    pub fn longer_hand_length(&self) -> u8 {
        self.north.len().max(self.south.len())
    }
}

impl fmt::Display for Combination {
    /// The notation, such as `AQT-xx`.
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}-{}", self.north_holding, self.south_holding)
    }
}

/// A combination and the number of tricks declarer wants from it.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Problem {
    pub combination: Combination,
    /// The number of tricks wanted.
    pub target: u8,
}

impl Problem {
    /// The problem of winning `target` tricks with `combination`. The target
    /// must be from 1 up to the longer hand's length.
    pub fn new(
        combination: Combination,
        target: u8,
    ) -> Result<Problem, NotationError> {
        let most_tricks = combination.longer_hand_length();
        if target == 0 || target > most_tricks {
            return Err(NotationError(format!(
                "target {target} for {combination} is outside 1 to \
                 {most_tricks}, the longer hand's length"
            )));
        }
        Ok(Problem {
            combination,
            target,
        })
    }
}

impl fmt::Display for Problem {
    /// The notation, such as `AQT-xx@2`.
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}@{}", self.combination, self.target)
    }
}

/// Parse a problem such as `AQT-xx@2`: North's holding, South's, and the
/// number of tricks wanted.
pub fn parse_problem(text: &str) -> Result<Problem, NotationError> {
    let (holdings, target_text) = text.split_once('@').ok_or_else(|| {
        NotationError(format!(
            "problem {text:?} names no target; write it as North-South@tricks, \
             such as AQT-xx@2"
        ))
    })?;
    // The first `-` separates the hands; a void can still be spelled `-`
    // after it, or `(void)` anywhere.
    let (north_text, south_text) =
        holdings.split_once('-').ok_or_else(|| {
            NotationError(format!(
                "problem {text:?} needs a - between North's and South's \
                 holdings"
            ))
        })?;
    let combination = Combination::new(
        parse_holding(north_text)?,
        parse_holding(south_text)?,
    )?;

    let target: u8 = target_text.trim().parse().map_err(|_| {
        NotationError(format!(
            "target {target_text:?} in problem {text:?} isn't a number of \
             tricks"
        ))
    })?;
    Problem::new(combination, target)
}
