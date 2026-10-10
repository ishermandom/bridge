// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The ways the defenders' cards can lie, and how likely each way is.
//!
//! Declarer's cards split the defenders' cards into groups: sets of the
//! defenders' cards with no declarer card ranked between them. Two cards in
//! one group beat and lose to exactly the same declarer cards, so which of
//! them a defender holds never changes how many tricks declarer takes. A
//! layout therefore records only how many cards of each group West holds;
//! East holds the rest.

use crate::cards::{Rank, RankSet, SUIT_SIZE};
use crate::layout_set::{LayoutSet, MAX_LAYOUTS};
use crate::notation::Combination;

/// The most groups any combination splits the defenders' cards into.
///
/// Each group sits just below a different declarer card, or above them all,
/// so there is at most one more group than declarer has cards. With 13 cards
/// in all, that peaks at 7 single-card groups alternating with 6 declarer
/// cards.
pub const MAX_GROUPS: usize = 7;

/// The number of ways to deal the defenders' 26 cards into two hands of 13.
pub const DEAL_COUNT: u64 = 10_400_600;

/// A defender.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Defender {
    West,
    East,
}

/// Defenders' cards that no declarer card separates.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct DefenderGroup {
    /// The group's ranks.
    pub ranks: RankSet,
}

impl DefenderGroup {
    /// The group's highest rank. It beats and loses to the same declarer
    /// cards as every other card in the group.
    pub fn top(self) -> Rank {
        self.ranks
            .highest()
            .expect("a group holds at least one card")
    }

    /// How many cards the group holds.
    pub fn size(self) -> u8 {
        self.ranks.len()
    }
}

/// Every layout of the defenders' cards for one combination, along with the
/// layout sets the solver asks about repeatedly, computed up front.
#[derive(Debug)]
pub struct Layouts {
    /// The combination whose missing cards these layouts deal out.
    pub combination: Combination,
    /// The defenders' groups, from highest to lowest.
    pub groups: Vec<DefenderGroup>,
    /// For each layout, how many cards of each group West holds.
    pub west_counts: Vec<[u8; MAX_GROUPS]>,
    /// For each layout, how many of the `DEAL_COUNT` deals have that layout.
    pub weights: Vec<u64>,
    /// Every layout.
    pub all: LayoutSet,
    /// `at_least[defender][group][count]`, indexed by `Defender`: the layouts
    /// where that defender holds at least `count` cards of the group.
    at_least: [Vec<Vec<LayoutSet>>; 2],
    /// `length[defender][count]`, indexed by `Defender`: the layouts where
    /// that defender holds exactly `count` cards of the suit.
    length: [Vec<LayoutSet>; 2],
}

impl Layouts {
    /// Every layout of the cards missing from `combination`.
    pub fn new(combination: Combination) -> Layouts {
        let groups = defender_groups(combination);
        let missing_count: u8 = groups.iter().map(|group| group.size()).sum();

        // Count through every West holding as a mixed-radix number, one digit
        // per group.
        let mut west_counts = Vec::new();
        let mut counts = [0u8; MAX_GROUPS];
        loop {
            west_counts.push(counts);
            let Some(digit) = (0..groups.len())
                .find(|&index| counts[index] < groups[index].size())
            else {
                break;
            };
            counts[digit] += 1;
            counts[..digit].fill(0);
        }
        assert!(west_counts.len() <= MAX_LAYOUTS);

        let weights = west_counts
            .iter()
            .map(|counts| layout_weight(&groups, counts, missing_count))
            .collect();

        let mut at_least = [Vec::new(), Vec::new()];
        let mut length = [
            vec![LayoutSet::EMPTY; usize::from(SUIT_SIZE) + 1],
            vec![LayoutSet::EMPTY; usize::from(SUIT_SIZE) + 1],
        ];
        for (index, group) in groups.iter().enumerate() {
            for defender_sets in &mut at_least {
                // Counts run up to one past the group's size, which no layout
                // reaches.
                defender_sets.push(vec![
                    LayoutSet::EMPTY;
                    usize::from(group.size()) + 2
                ]);
            }
            for (layout, counts) in west_counts.iter().enumerate() {
                let west = counts[index];
                let east = group.size() - west;
                for count in 0..=west {
                    at_least[0][index][usize::from(count)].insert(layout);
                }
                for count in 0..=east {
                    at_least[1][index][usize::from(count)].insert(layout);
                }
            }
        }
        for (layout, counts) in west_counts.iter().enumerate() {
            let west: u8 = counts.iter().sum();
            length[0][usize::from(west)].insert(layout);
            length[1][usize::from(missing_count - west)].insert(layout);
        }

        Layouts {
            combination,
            all: LayoutSet::first(west_counts.len()),
            groups,
            west_counts,
            weights,
            at_least,
            length,
        }
    }

    /// The layouts where `defender` holds at least `count` cards of the group
    /// at `group`.
    pub fn at_least(
        &self,
        defender: Defender,
        group: usize,
        count: u8,
    ) -> LayoutSet {
        let sets = &self.at_least[defender as usize][group];
        sets.get(usize::from(count))
            .copied()
            .unwrap_or(LayoutSet::EMPTY)
    }

    /// The layouts where `defender` holds exactly `count` cards of the suit.
    pub fn with_length(&self, defender: Defender, count: u8) -> LayoutSet {
        self.length[defender as usize][usize::from(count)]
    }

    /// How many deals have a layout in `layouts`.
    pub fn weight(&self, layouts: LayoutSet) -> u64 {
        layouts.indices().map(|layout| self.weights[layout]).sum()
    }

    /// How many cards of the suit `defender` holds in the layout at `layout`.
    pub fn length_of(&self, defender: Defender, layout: usize) -> u8 {
        let west: u8 = self.west_counts[layout].iter().sum();
        match defender {
            Defender::West => west,
            Defender::East => self.missing_count() - west,
        }
    }

    /// How many cards of the group at `group` `defender` holds in the layout
    /// at `layout`.
    pub fn count_of(
        &self,
        defender: Defender,
        group: usize,
        layout: usize,
    ) -> u8 {
        let west = self.west_counts[layout][group];
        match defender {
            Defender::West => west,
            Defender::East => self.groups[group].size() - west,
        }
    }

    /// How many cards of the suit the defenders hold between them.
    pub fn missing_count(&self) -> u8 {
        self.groups.iter().map(|group| group.size()).sum()
    }
}

/// The defenders' groups for `combination`, from highest to lowest.
fn defender_groups(combination: Combination) -> Vec<DefenderGroup> {
    let declarer = combination.north.union(combination.south);
    let mut groups = Vec::new();
    let mut current = RankSet::EMPTY;
    for rank in (0..SUIT_SIZE).rev() {
        if declarer.contains(rank) {
            if !current.is_empty() {
                groups.push(DefenderGroup { ranks: current });
                current = RankSet::EMPTY;
            }
        } else {
            current = current.with(rank);
        }
    }
    if !current.is_empty() {
        groups.push(DefenderGroup { ranks: current });
    }
    groups
}

/// How many deals give West exactly `west_counts` of each group.
///
/// West's hand is those suit cards, chosen from each group in
/// `C(size, count)` ways, filled out to 13 cards from the 26 −
/// `missing_count` non-suit cards the defenders hold.
fn layout_weight(
    groups: &[DefenderGroup],
    west_counts: &[u8; MAX_GROUPS],
    missing_count: u8,
) -> u64 {
    let west_length: u8 = west_counts.iter().sum();
    let suit_ways: u64 = groups
        .iter()
        .zip(west_counts)
        .map(|(group, &count)| binomial(group.size(), count))
        .product();
    let other_cards = 2 * SUIT_SIZE - missing_count;
    suit_ways * binomial(other_cards, SUIT_SIZE - west_length)
}

/// The number of ways to choose `chosen` items from `total`.
fn binomial(total: u8, chosen: u8) -> u64 {
    if chosen > total {
        return 0;
    }
    let chosen = chosen.min(total - chosen);
    // Each partial product is itself a binomial coefficient, so the division
    // is always exact.
    (0..u64::from(chosen)).fold(1, |product, index| {
        product * (u64::from(total) - index) / (index + 1)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notation::parse_problem;

    fn layouts_for(problem: &str) -> Layouts {
        let problem = parse_problem(problem).expect("a valid problem");
        Layouts::new(problem.combination)
    }

    #[test]
    fn binomial_matches_known_values() {
        assert_eq!(binomial(26, 13), DEAL_COUNT);
        assert_eq!(binomial(5, 2), 10);
        assert_eq!(binomial(3, 4), 0);
    }

    #[test]
    fn declarer_cards_split_the_missing_cards_into_groups() {
        let layouts = layouts_for("AQT-xx@2");

        let sizes: Vec<u8> =
            layouts.groups.iter().map(|group| group.size()).collect();
        // The K; the J; and the 9 down to the 4.
        assert_eq!(sizes, vec![1, 1, 6]);
        assert_eq!(layouts.west_counts.len(), 2 * 2 * 7);
    }

    #[test]
    fn layout_weights_cover_every_deal() {
        for problem in ["AQT-xx@2", "KJxx-A9xx@3", "A-x@1", "AKQJT98765432--@1"]
        {
            let layouts = layouts_for(problem);
            assert_eq!(layouts.weight(layouts.all), DEAL_COUNT, "{problem}");
        }
    }

    #[test]
    fn a_single_card_is_equally_likely_with_either_defender() {
        let layouts = layouts_for("AQ-xx@2");
        let king_with_west = layouts.at_least(Defender::West, 0, 1);

        assert_eq!(2 * layouts.weight(king_with_west), DEAL_COUNT);
    }

    #[test]
    fn length_sets_partition_the_layouts() {
        let layouts = layouts_for("KQx-xxx@2");
        let lengths = (0..=SUIT_SIZE)
            .map(|count| layouts.with_length(Defender::East, count))
            .fold(LayoutSet::EMPTY, LayoutSet::union);

        assert_eq!(lengths, layouts.all);
    }
}
