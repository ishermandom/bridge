// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Cards within a single suit: ranks, and sets of ranks.

/// A card's rank within the suit, from 0 for the deuce up to 12 for the ace.
pub type Rank = u8;

/// The number of cards in a suit.
pub const SUIT_SIZE: u8 = 13;

/// The ace's rank, the highest in the suit.
pub const ACE: Rank = 12;

/// Each rank's symbol in the notation, indexed by rank.
const RANK_SYMBOLS: [char; SUIT_SIZE as usize] = [
    '2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A',
];

/// The notation's symbol for `rank`, such as `T` for the ten.
pub fn rank_symbol(rank: Rank) -> char {
    RANK_SYMBOLS[usize::from(rank)]
}

/// The rank that `symbol` names, if it names one.
pub fn rank_for_symbol(symbol: char) -> Option<Rank> {
    let position = RANK_SYMBOLS.iter().position(|&each| each == symbol)?;
    // A position in a 13-element array always fits in a `Rank`.
    Some(position as Rank)
}

/// A set of ranks within the suit, one bit per rank.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default, Debug)]
pub struct RankSet(u16);

impl RankSet {
    /// The set holding no ranks.
    pub const EMPTY: RankSet = RankSet(0);

    /// The set holding every rank in the suit.
    pub const ALL: RankSet = RankSet((1 << SUIT_SIZE) - 1);

    /// The set holding only `rank`.
    pub fn single(rank: Rank) -> RankSet {
        RankSet(1 << rank)
    }

    /// The ranks strictly between `high` and `low`, exclusive of both.
    pub fn strictly_between(high: Rank, low: Rank) -> RankSet {
        if high <= low + 1 {
            return RankSet::EMPTY;
        }
        let below_high = (1u16 << high) - 1;
        let up_to_low = (1u16 << (low + 1)) - 1;
        RankSet(below_high & !up_to_low)
    }

    /// The ranks strictly above `rank`.
    pub fn above(rank: Rank) -> RankSet {
        let up_to_rank = (1u16 << (rank + 1)) - 1;
        RankSet(RankSet::ALL.0 & !up_to_rank)
    }

    /// Whether the set holds `rank`.
    pub fn contains(self, rank: Rank) -> bool {
        self.0 & (1 << rank) != 0
    }

    /// This set plus `rank`.
    pub fn with(self, rank: Rank) -> RankSet {
        RankSet(self.0 | (1 << rank))
    }

    /// This set minus `rank`.
    pub fn without(self, rank: Rank) -> RankSet {
        RankSet(self.0 & !(1 << rank))
    }

    /// The ranks in either set.
    pub fn union(self, other: RankSet) -> RankSet {
        RankSet(self.0 | other.0)
    }

    /// The ranks in both sets.
    pub fn intersection(self, other: RankSet) -> RankSet {
        RankSet(self.0 & other.0)
    }

    /// The ranks in this set but not in `other`.
    pub fn difference(self, other: RankSet) -> RankSet {
        RankSet(self.0 & !other.0)
    }

    /// How many ranks the set holds.
    pub fn len(self) -> u8 {
        // At most 13 bits are ever set.
        self.0.count_ones() as u8
    }

    /// Whether the set holds no ranks.
    pub fn is_empty(self) -> bool {
        self.0 == 0
    }

    /// The highest rank in the set, if any.
    pub fn highest(self) -> Option<Rank> {
        if self.is_empty() {
            return None;
        }
        // The index of the top set bit, which is below 16.
        Some((15 - self.0.leading_zeros()) as Rank)
    }

    /// The lowest rank in the set, if any.
    pub fn lowest(self) -> Option<Rank> {
        if self.is_empty() {
            return None;
        }
        Some(self.0.trailing_zeros() as Rank)
    }

    /// The set's ranks from highest to lowest.
    pub fn descending(self) -> impl Iterator<Item = Rank> {
        (0..SUIT_SIZE)
            .rev()
            .filter(move |&rank| self.contains(rank))
    }
}
