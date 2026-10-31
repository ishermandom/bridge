// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! An independent check of the analyzer's chances, from a deliberately simple
//! solver.
//!
//! The analyzer treats each group of the defenders' interchangeable cards as
//! one card, and tries only one of each set of declarer's equal cards, as
//! `suit_combinations/spec.md` #interchangeable-cards argues it may. This
//! solver does neither: every missing card lies with West or East on its
//! own, every card is a play of its own, and nothing is cut short. Where the
//! two agree, those shortcuts changed nothing.

use std::collections::HashMap;

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// A set of layouts, one bit per layout.
type LayoutBits = Vec<u64>;

/// One problem's layouts and their weights, with the frontiers solved so
/// far.
struct Game {
    /// For each layout, West's cards and East's, as rank bitmasks.
    hands: Vec<(u16, u16)>,
    /// For each layout, how many deals have it.
    weights: Vec<u64>,
    target: u8,
    /// How many 64-bit words a `LayoutBits` needs.
    word_count: usize,
    /// The frontier from each state solved so far.
    cache: HashMap<State, Vec<LayoutBits>>,
}

/// What declarer has seen at the start of a trick.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
struct State {
    north: u16,
    south: u16,
    west_played: u16,
    east_played: u16,
    has_west_shown_out: bool,
    has_east_shown_out: bool,
    tricks_won: u8,
}

/// A defender's play: a card, or none when showing out.
type DefenderCard = Option<u8>;

impl Game {
    fn new(north: u16, south: u16, target: u8) -> Game {
        let missing: Vec<u8> = (0..13)
            .filter(|&rank| (north | south) & (1 << rank) == 0)
            .collect();
        let count = missing.len();
        let mut hands = Vec::new();
        let mut weights = Vec::new();
        // Each bit of `layout` says whether West holds the matching missing
        // card.
        for layout in 0..(1u32 << count) {
            let mut west = 0u16;
            let mut east = 0u16;
            for (index, &rank) in missing.iter().enumerate() {
                if layout & (1 << index) != 0 {
                    west |= 1 << rank;
                } else {
                    east |= 1 << rank;
                }
            }
            hands.push((west, east));
            let west_length = west.count_ones() as u64;
            // West's other cards come from the defenders' 26 − count cards in
            // other suits.
            weights.push(binomial(26 - count as u64, 13 - west_length));
        }
        let word_count = hands.len().div_ceil(64);
        Game {
            hands,
            weights,
            target,
            word_count,
            cache: HashMap::new(),
        }
    }

    fn weight(&self, set: &LayoutBits) -> u64 {
        (0..self.hands.len())
            .filter(|&layout| set[layout / 64] & (1 << (layout % 64)) != 0)
            .map(|layout| self.weights[layout])
            .sum()
    }

    /// The layouts where `holds` is true.
    fn layouts_where(&self, holds: impl Fn(u16, u16) -> bool) -> LayoutBits {
        let mut set = vec![0u64; self.word_count];
        for (layout, &(west, east)) in self.hands.iter().enumerate() {
            if holds(west, east) {
                set[layout / 64] |= 1 << (layout % 64);
            }
        }
        set
    }

    /// The layouts consistent with what the defenders have played in
    /// `state`.
    fn possible_layouts(&self, state: &State) -> LayoutBits {
        self.layouts_where(|west, east| {
            west & state.west_played == state.west_played
                && east & state.east_played == state.east_played
                && (!state.has_west_shown_out || west == state.west_played)
                && (!state.has_east_shown_out || east == state.east_played)
        })
    }

    /// The most deals any strategy wins from the start.
    fn best_weight(&mut self, north: u16, south: u16) -> u64 {
        let start = State {
            north,
            south,
            west_played: 0,
            east_played: 0,
            has_west_shown_out: false,
            has_east_shown_out: false,
            tricks_won: 0,
        };
        let frontier = self.solve(start);
        frontier
            .iter()
            .map(|set| self.weight(set))
            .max()
            .unwrap_or(0)
    }

    fn solve(&mut self, state: State) -> Vec<LayoutBits> {
        if let Some(frontier) = self.cache.get(&state) {
            return frontier.clone();
        }
        let possible = self.possible_layouts(&state);
        let rounds = state.north.count_ones().max(state.south.count_ones());
        let frontier = if state.tricks_won >= self.target {
            vec![possible]
        } else if u32::from(state.tricks_won) + rounds < u32::from(self.target)
        {
            vec![vec![0; self.word_count]]
        } else {
            let mut frontier = Vec::new();
            for (is_north, cards) in [(true, state.north), (false, state.south)]
            {
                for lead in ranks(cards) {
                    let child =
                        self.second_hand_turn(state, &possible, is_north, lead);
                    for set in child {
                        insert(&mut frontier, set);
                    }
                }
            }
            frontier
        };
        self.cache.insert(state, frontier.clone());
        frontier
    }

    /// Each play the defender may make, with the layouts allowing it. A
    /// defender who holds no card left can only show out.
    fn defender_plays(
        &self,
        state: &State,
        possible: &LayoutBits,
        is_west: bool,
    ) -> Vec<(DefenderCard, LayoutBits)> {
        let played = if is_west {
            state.west_played
        } else {
            state.east_played
        };
        let mut plays = Vec::new();
        for card in 0..13u8 {
            let mask = self.layouts_where(|west, east| {
                let hand = if is_west { west } else { east };
                hand & (1 << card) != 0 && played & (1 << card) == 0
            });
            let mask = intersection(possible, &mask);
            if mask.iter().any(|&word| word != 0) {
                plays.push((Some(card), mask));
            }
        }
        let void = self.layouts_where(|west, east| {
            let hand = if is_west { west } else { east };
            hand & !played == 0
        });
        let void = intersection(possible, &void);
        if void.iter().any(|&word| word != 0) {
            plays.push((None, void));
        }
        plays
    }

    /// The frontier when second hand is due to play to `lead`.
    fn second_hand_turn(
        &mut self,
        state: State,
        possible: &LayoutBits,
        is_north: bool,
        lead: u8,
    ) -> Vec<LayoutBits> {
        // North leads to East; South leads to West.
        let second_is_west = !is_north;
        let plays = self.defender_plays(&state, possible, second_is_west);
        // Start from a frontier that wins in every possible layout, which
        // combining leaves unchanged.
        let mut combined = vec![possible.clone()];
        for (card, mask) in plays {
            let mut child_state = state;
            record(&mut child_state, second_is_west, card);
            let child_possible = self.possible_layouts(&child_state);
            let mut child = Vec::new();
            let partner = if is_north { state.south } else { state.north };
            let thirds: Vec<Option<u8>> = if partner == 0 {
                vec![None]
            } else {
                ranks(partner).map(Some).collect()
            };
            for third in thirds {
                for set in self.fourth_hand_turn(
                    child_state,
                    &child_possible,
                    is_north,
                    lead,
                    card,
                    third,
                ) {
                    insert(&mut child, set);
                }
            }
            combined = combine(&combined, &child, possible, &mask);
        }
        combined
    }

    /// The frontier when fourth hand is due to play.
    fn fourth_hand_turn(
        &mut self,
        state: State,
        possible: &LayoutBits,
        is_north: bool,
        lead: u8,
        second: DefenderCard,
        third: Option<u8>,
    ) -> Vec<LayoutBits> {
        let fourth_is_west = is_north;
        let plays = self.defender_plays(&state, possible, fourth_is_west);
        // Start from a frontier that wins in every possible layout, which
        // combining leaves unchanged.
        let mut combined = vec![possible.clone()];
        for (card, mask) in plays {
            let mut next = state;
            record(&mut next, fourth_is_west, card);
            let declarer_best = third.map_or(lead, |third| third.max(lead));
            let defender_best = [second, card].into_iter().flatten().max();
            if defender_best.is_none_or(|best| declarer_best > best) {
                next.tricks_won += 1;
            }
            if is_north {
                next.north &= !(1 << lead);
                if let Some(third) = third {
                    next.south &= !(1 << third);
                }
            } else {
                next.south &= !(1 << lead);
                if let Some(third) = third {
                    next.north &= !(1 << third);
                }
            }
            let child = self.solve(next);
            combined = combine(&combined, &child, possible, &mask);
        }
        combined
    }
}

/// Record a defender's play in `state`.
fn record(state: &mut State, is_west: bool, card: DefenderCard) {
    match (is_west, card) {
        (true, Some(card)) => state.west_played |= 1 << card,
        (false, Some(card)) => state.east_played |= 1 << card,
        (true, None) => state.has_west_shown_out = true,
        (false, None) => state.has_east_shown_out = true,
    }
}

/// Fold one more defender play's frontier into `combined`: a layout succeeds
/// only where both do, counting the play's part as a success in the
/// possible layouts outside `mask`, where that play can't happen.
fn combine(
    combined: &[LayoutBits],
    child: &[LayoutBits],
    possible: &LayoutBits,
    mask: &LayoutBits,
) -> Vec<LayoutBits> {
    let outside: LayoutBits = possible
        .iter()
        .zip(mask)
        .map(|(possible, mask)| possible & !mask)
        .collect();
    let mut result = Vec::new();
    for left in combined {
        for right in child {
            let set = left
                .iter()
                .zip(right)
                .zip(&outside)
                .map(|((left, right), outside)| left & (right | outside))
                .collect();
            insert(&mut result, set);
        }
    }
    result
}

/// Add `set` to `frontier` unless a superset is there, dropping its subsets.
fn insert(frontier: &mut Vec<LayoutBits>, set: LayoutBits) {
    let contains = |big: &LayoutBits, small: &LayoutBits| {
        big.iter().zip(small).all(|(big, small)| small & !big == 0)
    };
    // TODO: if a check whose frontiers reach thousands of sets, such as
    // KQT-xxx@2, stops being ignored, keep `frontier` sorted from the largest
    // set down. Then only the sets before `set`'s place can contain it, and
    // only those after can be its subsets; in a trial, that halved
    // KQT-xxx@2's time.
    if frontier.iter().any(|existing| contains(existing, &set)) {
        return;
    }
    frontier.retain(|existing| !contains(&set, existing));
    frontier.push(set);
}

fn intersection(left: &LayoutBits, right: &LayoutBits) -> LayoutBits {
    left.iter()
        .zip(right)
        .map(|(left, right)| left & right)
        .collect()
}

/// The ranks in `cards`, a rank bitmask.
fn ranks(cards: u16) -> impl Iterator<Item = u8> {
    (0..13u8).filter(move |&rank| cards & (1 << rank) != 0)
}

fn binomial(total: u64, chosen: u64) -> u64 {
    (0..chosen)
        .fold(1, |product, index| product * (total - index) / (index + 1))
}

/// The brute-force chance and the analyzer's, both as percentages to six
/// decimal places.
fn both_chances(problem: &str) -> (String, String) {
    let parsed = parse_problem(problem).expect("a valid problem");
    let bitmask_of = |set: suit_combinations::cards::RankSet| {
        set.descending().fold(0u16, |mask, rank| mask | (1 << rank))
    };
    let north = bitmask_of(parsed.combination.north);
    let south = bitmask_of(parsed.combination.south);
    let mut game = Game::new(north, south, parsed.target);
    let brute = game.best_weight(north, south);
    let analysis = analyze(parsed);
    (
        format!("{:.6}", 100.0 * brute as f64 / 10_400_600.0),
        format!("{:.6}", analysis.success_percent()),
    )
}

/// Assert that the two solvers agree on `problem`.
fn assert_agrees(problem: &str) {
    let (brute, analyzer) = both_chances(problem);
    assert_eq!(brute, analyzer, "{problem}");
}

/// Random combinations with at most `max_missing` cards missing, as
/// problems such as `AQ9x-K8xx@3`, from a fixed seed so that a
/// disagreement can be found again.
fn random_problems(count: usize, max_missing: u32, seed: u64) -> Vec<String> {
    const SYMBOLS: &[u8] = b"23456789TJQKA";
    let mut state = seed;
    let mut next = move || {
        // xorshift64.
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let mut problems = Vec::new();
    while problems.len() < count {
        let mut north = String::new();
        let mut south = String::new();
        for rank in (0..13).rev() {
            // Each card goes to North, to South, or to the defenders, one
            // time in three each.
            match next() % 3 {
                0 => north.push(SYMBOLS[rank] as char),
                1 => south.push(SYMBOLS[rank] as char),
                _ => {}
            }
        }
        let missing = 13 - (north.len() + south.len()) as u32;
        if missing > max_missing || north.is_empty() || south.is_empty() {
            continue;
        }
        let most_tricks = north.len().max(south.len()) as u64;
        let target = 1 + next() % most_tricks;
        problems.push(format!("{north}-{south}@{target}"));
    }
    problems
}

#[test]
#[ignore = "takes a while; run with --ignored to check 300 combinations"]
fn random_combinations_agree() {
    let disagreements: Vec<(String, String, String)> =
        random_problems(300, 6, 2026)
            .into_iter()
            .filter_map(|problem| {
                let (brute, analyzer) = both_chances(&problem);
                (brute != analyzer).then_some((problem, brute, analyzer))
            })
            .collect();
    assert!(disagreements.is_empty(), "{disagreements:?}");
}

#[test]
fn a_simple_finesse_agrees() {
    assert_agrees("AQ-xx@2");
}

#[test]
fn a_finesse_of_the_king_agrees() {
    assert_agrees("Kx-xx@1");
}

#[test]
fn a_finesse_against_two_honors_agrees() {
    assert_agrees("AJ9-xx@2");
}

#[test]
#[ignore = "takes a while; run with --ignored"]
fn a_hold_up_of_the_ace_agrees() {
    assert_agrees("KQT-xxx@2");
}

#[test]
fn a_two_way_finesse_agrees() {
    assert_agrees("Axx-KJT@3");
}

#[test]
fn a_safety_play_agrees() {
    assert_agrees("KJxx-A9xx@3");
}

#[test]
fn a_long_suit_agrees() {
    assert_agrees("AQxxx-J9xx@5");
}
