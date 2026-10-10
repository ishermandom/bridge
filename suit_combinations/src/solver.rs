// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The search for declarer's best strategies against best defense.
//!
//! The model is set out in `suit_combinations/spec.md` #model. In short:
//! declarer leads every trick, from either hand; the defenders see every card
//! and know declarer's strategy; and declarer sees only the cards played.
//!
//! A strategy's result is the set of layouts where it reaches each target,
//! and the search keeps every result that no other strategy beats outright.
//! At declarer's turn, any one choice of play is open, so the results gather
//! the results of every choice. At a defender's turn, the defenders choose
//! separately in each layout, so a strategy succeeds in a layout only if it
//! succeeds after every play that defender could make there. Combining one
//! result per play this way covers every strategy, since declarer may plan
//! differently after each play the defender makes.

use std::rc::Rc;

use rustc_hash::FxHashMap;

use crate::cards::{Rank, RankSet, SUIT_SIZE};
use crate::layout_set::LayoutSet;
use crate::layouts::{Defender, Layouts};

/// One of declarer's hands.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Hand {
    North,
    South,
}

impl Hand {
    /// The other of declarer's hands.
    pub fn partner(self) -> Hand {
        match self {
            Hand::North => Hand::South,
            Hand::South => Hand::North,
        }
    }

    /// The defender who plays second when this hand leads.
    pub fn next_defender(self) -> Defender {
        match self {
            Hand::North => Defender::East,
            Hand::South => Defender::West,
        }
    }

    /// The defender who plays last when this hand leads.
    pub fn last_defender(self) -> Defender {
        match self {
            Hand::North => Defender::West,
            Hand::South => Defender::East,
        }
    }
}

/// How many cards a defender has played from each group, four bits per
/// group.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default, Debug)]
pub struct PlayedCounts(u32);

impl PlayedCounts {
    /// How many cards of the group at `group` have been played.
    pub fn get(self, group: usize) -> u8 {
        // Four bits hold any group size.
        ((self.0 >> (4 * group)) & 0xF) as u8
    }

    /// These counts with one more card played from the group at `group`.
    pub fn incremented(self, group: usize) -> PlayedCounts {
        PlayedCounts(self.0 + (1 << (4 * group)))
    }

    /// How many cards have been played in all.
    pub fn total(self) -> u8 {
        (0..8).map(|group| self.get(group)).sum()
    }
}

/// What declarer can see of the play so far: the cards left in each of
/// declarer's hands, what each defender has played, and the tricks won.
///
/// Every layout that fits what the defenders have played remains possible, so
/// the position also fixes which layouts declarer must still allow for.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct Position {
    /// North's cards left at the start of the current trick.
    pub north: RankSet,
    /// South's cards left at the start of the current trick.
    pub south: RankSet,
    /// What each defender has played, indexed by `Defender`.
    pub played: [PlayedCounts; 2],
    /// Whether each defender has shown out, indexed by `Defender`.
    pub shown_out: [bool; 2],
    /// The tricks declarer has won.
    pub tricks_won: u8,
}

impl Position {
    /// The position before any card is played.
    pub fn start(layouts: &Layouts) -> Position {
        Position {
            north: layouts.combination.north,
            south: layouts.combination.south,
            played: [PlayedCounts::default(); 2],
            shown_out: [false; 2],
            tricks_won: 0,
        }
    }

    /// The cards left in `hand`.
    pub fn hand(self, hand: Hand) -> RankSet {
        match hand {
            Hand::North => self.north,
            Hand::South => self.south,
        }
    }

    /// This position with `hand` holding `cards`.
    fn with_hand(self, hand: Hand, cards: RankSet) -> Position {
        match hand {
            Hand::North => Position {
                north: cards,
                ..self
            },
            Hand::South => Position {
                south: cards,
                ..self
            },
        }
    }

    /// This position after `defender` plays `play`.
    fn after_defender_play(
        self,
        defender: Defender,
        play: DefenderPlay,
    ) -> Position {
        let mut next = self;
        match play {
            DefenderPlay::Group(group) => {
                next.played[defender as usize] =
                    self.played[defender as usize].incremented(group);
            }
            DefenderPlay::ShowOut => next.shown_out[defender as usize] = true,
        }
        next
    }
}

/// What a defender plays to a trick.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum DefenderPlay {
    /// A card from the group at this index.
    Group(usize),
    /// A card of another suit, having none of this one.
    ShowOut,
}

/// What the hand opposite the leader plays to a trick.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum FollowPlay {
    /// A card of the suit.
    Card(Rank),
    /// A card of another suit, having none of this one.
    Discard,
}

/// A trick in progress: the lead, and whatever has followed it.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct Trick {
    /// The position, counting the defenders' plays to this trick so far.
    /// Declarer's cards leave the hands only once the trick is complete, in
    /// `next_position`.
    pub position: Position,
    /// The hand that led.
    pub leader: Hand,
    /// The card led.
    pub lead: Rank,
    /// The second hand's play, once made.
    pub second: Option<DefenderPlay>,
    /// The third hand's play, once made.
    pub third: Option<FollowPlay>,
    /// The fourth hand's play, once made.
    pub fourth: Option<DefenderPlay>,
}

impl Trick {
    /// A trick that `leader` has just led `lead` to.
    pub fn led(position: Position, leader: Hand, lead: Rank) -> Trick {
        Trick {
            position,
            leader,
            lead,
            second: None,
            third: None,
            fourth: None,
        }
    }

    /// The defender due to play next: second hand, or else fourth.
    pub fn defender_to_play(self) -> Defender {
        if self.second.is_none() {
            self.leader.next_defender()
        } else {
            self.leader.last_defender()
        }
    }

    /// This trick after the defender due to play plays `play`.
    pub fn with_defender_play(self, play: DefenderPlay) -> Trick {
        let defender = self.defender_to_play();
        let position = self.position.after_defender_play(defender, play);
        if self.second.is_none() {
            Trick {
                position,
                second: Some(play),
                ..self
            }
        } else {
            Trick {
                position,
                fourth: Some(play),
                ..self
            }
        }
    }

    /// This trick after the third hand plays `play`.
    pub fn with_third(self, play: FollowPlay) -> Trick {
        Trick {
            third: Some(play),
            ..self
        }
    }

    /// The highest card declarer has played to the trick.
    fn declarer_best(self) -> Rank {
        match self.third {
            Some(FollowPlay::Card(card)) => card.max(self.lead),
            _ => self.lead,
        }
    }

    /// Whether declarer wins the completed trick.
    pub fn declarer_wins(self, layouts: &Layouts) -> bool {
        let defender_best = [self.second, self.fourth]
            .into_iter()
            .flatten()
            .filter_map(|play| match play {
                DefenderPlay::Group(group) => Some(layouts.groups[group].top()),
                DefenderPlay::ShowOut => None,
            })
            .max();
        defender_best.is_none_or(|best| self.declarer_best() > best)
    }

    /// The position after the completed trick.
    pub fn next_position(self, layouts: &Layouts) -> Position {
        let leader_cards = self.position.hand(self.leader).without(self.lead);
        let mut next = self.position.with_hand(self.leader, leader_cards);
        if let Some(FollowPlay::Card(card)) = self.third {
            let partner = self.leader.partner();
            next = next.with_hand(partner, next.hand(partner).without(card));
        }
        if self.declarer_wins(layouts) {
            next.tricks_won += 1;
        }
        next
    }
}

/// The results of the strategies that no other strategy beats outright.
///
/// Each result holds one layout set per target, from the solver's lowest
/// target up: the layouts where the strategy wins at least that many tricks.
/// One result beats another outright when each of its sets contains the
/// other's.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Frontier {
    /// How many sets each result holds.
    level_count: usize,
    /// The results, one after another.
    sets: Vec<LayoutSet>,
    /// Each result's signature, in the same order.
    signatures: Vec<Signature>,
}

/// What a quick test needs to know about a result: a result can only contain
/// another when it holds at least as many layouts in all and the fold of its
/// set at the lowest target contains the other's.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct Signature {
    /// How many layouts the result's sets hold between them.
    size: u32,
    /// The fold of the result's set at the lowest target; see
    /// `LayoutSet::folded`.
    folded: u64,
}

impl Signature {
    /// The signature of `result`.
    fn of(result: &[LayoutSet]) -> Signature {
        Signature {
            // At most 13 sets of at most 162 layouts.
            size: result.iter().map(|set| set.len() as u32).sum(),
            folded: result[0].folded(),
        }
    }

    /// Whether a result with this signature might contain one with
    /// `other`.
    fn may_contain(self, other: Signature) -> bool {
        self.size >= other.size && self.folded & other.folded == other.folded
    }
}

impl Frontier {
    /// A frontier with no results yet.
    fn new(level_count: usize) -> Frontier {
        Frontier {
            level_count,
            sets: Vec::new(),
            signatures: Vec::new(),
        }
    }

    /// A frontier holding only `result`.
    fn single(result: &[LayoutSet]) -> Frontier {
        Frontier {
            level_count: result.len(),
            sets: result.to_vec(),
            signatures: vec![Signature::of(result)],
        }
    }

    /// The results, each one layout set per target.
    pub fn results(&self) -> impl Iterator<Item = &[LayoutSet]> {
        self.sets.chunks_exact(self.level_count)
    }

    /// How many results the frontier holds.
    pub fn len(&self) -> usize {
        self.sets.len() / self.level_count
    }

    /// Whether the frontier holds no results.
    pub fn is_empty(&self) -> bool {
        self.sets.is_empty()
    }

    /// Whether some result wins, at every target, in every layout that
    /// `required` lists for that target.
    pub fn achieves(&self, required: &[LayoutSet]) -> bool {
        self.results().any(|result| covers(result, required))
    }

    /// Add `result`, unless a result already here beats or equals it,
    /// dropping any result that it beats.
    fn insert(&mut self, result: &[LayoutSet]) {
        let signature = Signature::of(result);
        let size = self.level_count;
        let is_beaten =
            self.signatures.iter().enumerate().any(|(index, existing)| {
                existing.may_contain(signature)
                    && covers(
                        &self.sets[index * size..(index + 1) * size],
                        result,
                    )
            });
        if is_beaten {
            return;
        }
        let mut kept = 0;
        for index in 0..self.signatures.len() {
            let range = index * size..(index + 1) * size;
            let is_dropped = signature.may_contain(self.signatures[index])
                && covers(result, &self.sets[range.clone()]);
            if !is_dropped {
                if kept != index {
                    self.sets.copy_within(range, kept * size);
                    self.signatures[kept] = self.signatures[index];
                }
                kept += 1;
            }
        }
        self.sets.truncate(kept * size);
        self.signatures.truncate(kept);
        self.sets.extend_from_slice(result);
        self.signatures.push(signature);
    }

    /// Add every result of `other`.
    fn merge(&mut self, other: &Frontier) {
        for result in other.results() {
            self.insert(result);
        }
    }

    /// Every pairing of one of these results with one of `child`'s, as at a
    /// defender's turn: `child` is the frontier after one of the defender's
    /// plays, and `outside` holds the layouts where that play can't happen.
    ///
    /// Each combined result succeeds in a layout only where both parts do,
    /// counting the child's part as a success wherever the child can't arise.
    fn combined_with(&self, child: &Frontier, outside: LayoutSet) -> Frontier {
        let mut combined = Frontier::new(self.level_count);
        let mut candidate = vec![LayoutSet::EMPTY; self.level_count];
        for result in self.results() {
            for child_result in child.results() {
                for level in 0..self.level_count {
                    candidate[level] = result[level]
                        .intersection(child_result[level].union(outside));
                }
                combined.insert(&candidate);
            }
        }
        combined
    }
}

/// The cards of `cards` reachable from `card` without crossing a rank in
/// `blockers`, including `card` itself.
fn run_around(cards: RankSet, card: Rank, blockers: RankSet) -> RankSet {
    let mut run = RankSet::single(card);
    for rank in card + 1..SUIT_SIZE {
        if blockers.contains(rank) {
            break;
        }
        if cards.contains(rank) {
            run = run.with(rank);
        }
    }
    for rank in (0..card).rev() {
        if blockers.contains(rank) {
            break;
        }
        if cards.contains(rank) {
            run = run.with(rank);
        }
    }
    run
}

/// Whether `result` reaches every target wherever `required` does.
pub fn covers(result: &[LayoutSet], required: &[LayoutSet]) -> bool {
    result
        .iter()
        .zip(required)
        .all(|(have, need)| have.is_superset(*need))
}

/// The search for one combination's best strategies, over a range of targets.
pub struct Solver<'a> {
    /// The combination's layouts.
    pub layouts: &'a Layouts,
    /// The target that each result's first set counts toward.
    pub lowest_target: u8,
    /// How many targets each result tracks.
    pub level_count: usize,
    /// The frontier from each position reached at the start of a trick.
    memo: FxHashMap<Position, Rc<Frontier>>,
    /// The frontier from each point within a trick, kept only once
    /// `remember_tricks` is called. The search reaches each such point once,
    /// but describing a line asks about the same points again and again.
    trick_memo: Option<FxHashMap<Trick, Rc<Frontier>>>,
}

impl<'a> Solver<'a> {
    /// A solver tracking every target from `lowest_target` to
    /// `highest_target`.
    pub fn new(
        layouts: &'a Layouts,
        lowest_target: u8,
        highest_target: u8,
    ) -> Solver<'a> {
        assert!(lowest_target >= 1 && lowest_target <= highest_target);
        Solver {
            layouts,
            lowest_target,
            level_count: usize::from(highest_target - lowest_target + 1),
            memo: FxHashMap::default(),
            trick_memo: None,
        }
    }

    /// Keep the frontier from each point within a trick from now on.
    pub fn remember_tricks(&mut self) {
        self.trick_memo.get_or_insert_with(FxHashMap::default);
    }

    /// The frontier at `trick` from the trick memo, or else from `compute`,
    /// remembered when the memo is on.
    fn within_trick(
        &mut self,
        trick: Trick,
        compute: fn(&mut Self, Trick) -> Rc<Frontier>,
    ) -> Rc<Frontier> {
        if let Some(frontier) =
            self.trick_memo.as_ref().and_then(|memo| memo.get(&trick))
        {
            return Rc::clone(frontier);
        }
        let frontier = compute(self, trick);
        if let Some(memo) = self.trick_memo.as_mut() {
            memo.insert(trick, Rc::clone(&frontier));
        }
        frontier
    }

    /// The layouts that fit what the defenders have played in `position`.
    pub fn live(&self, position: Position) -> LayoutSet {
        let mut live = self.layouts.all;
        for defender in [Defender::West, Defender::East] {
            let played = position.played[defender as usize];
            for group in 0..self.layouts.groups.len() {
                live = live.intersection(self.layouts.at_least(
                    defender,
                    group,
                    played.get(group),
                ));
            }
            if position.shown_out[defender as usize] {
                live = live.intersection(
                    self.layouts.with_length(defender, played.total()),
                );
            }
        }
        live
    }

    /// The frontier from `position`, at the start of a trick.
    pub fn solve(&mut self, position: Position) -> Rc<Frontier> {
        if let Some(frontier) = self.memo.get(&position) {
            return Rc::clone(frontier);
        }
        let frontier = Rc::new(self.solve_uncached(position));
        self.memo.insert(position, Rc::clone(&frontier));
        frontier
    }

    /// The frontier from `position`, computed afresh.
    fn solve_uncached(&mut self, position: Position) -> Frontier {
        let live = self.live(position);
        if let Some(result) = self.settled_result(position, live) {
            return Frontier::single(&result);
        }
        let mut frontier = Frontier::new(self.level_count);
        for (leader, lead) in self.leads(position) {
            let after = self.after_lead(Trick::led(position, leader, lead));
            frontier.merge(&after);
        }
        frontier
    }

    /// Every lead worth trying from `position`.
    pub fn leads(&self, position: Position) -> Vec<(Hand, Rank)> {
        [Hand::North, Hand::South]
            .into_iter()
            .flat_map(|hand| {
                self.distinct_plays(
                    position,
                    position.hand(hand),
                    RankSet::EMPTY,
                )
                .into_iter()
                .map(move |card| (hand, card))
            })
            .collect()
    }

    /// The result from `position` if no choice of play can change it, or
    /// else None.
    ///
    /// Targets up to the tricks already won plus the sure winners are
    /// certain; targets beyond the tricks already won plus one per round
    /// left are out of reach. Once every target is one or the other, play
    /// no longer matters.
    fn settled_result(
        &self,
        position: Position,
        live: LayoutSet,
    ) -> Option<Vec<LayoutSet>> {
        let rounds_left = position.north.len().max(position.south.len());
        let sure = self.sure_tricks(position).min(rounds_left);
        let certain_through = position.tricks_won + sure;
        let possible_through = position.tricks_won + rounds_left;
        let mut result = Vec::with_capacity(self.level_count);
        for level in 0..self.level_count {
            // `level` is below `level_count`, which fits in a `u8`.
            let target = self.lowest_target + level as u8;
            if target <= certain_through {
                result.push(live);
            } else if target > possible_through {
                result.push(LayoutSet::EMPTY);
            } else {
                return None;
            }
        }
        Some(result)
    }

    /// How many of declarer's cards outrank every defender's card left.
    pub fn sure_tricks(&self, position: Position) -> u8 {
        let declarer = position.north.union(position.south);
        match self.missing_ranks(position).highest() {
            Some(highest) => {
                declarer.intersection(RankSet::above(highest)).len()
            }
            None => declarer.len(),
        }
    }

    /// The ranks of every defender group with a card still unplayed.
    pub fn missing_ranks(&self, position: Position) -> RankSet {
        let mut ranks = RankSet::EMPTY;
        for (index, group) in self.layouts.groups.iter().enumerate() {
            let played =
                position.played[0].get(index) + position.played[1].get(index);
            if played < group.size() {
                ranks = ranks.union(group.ranks);
            }
        }
        ranks
    }

    /// One card for each distinct play from `cards`, where `contested` holds
    /// the ranks of any defender's card already played to this trick.
    ///
    /// Cards with no defender card left between them take the same tricks,
    /// so one stands for all; a card already played to the trick still
    /// counts as left, since declarer's card may yet beat it.
    ///
    /// Among equivalent cards, the one chosen is the top of the lowest
    /// sequence, a sequence being cards with nothing at all left between
    /// them: within a sequence every card is the same in every respect, and
    /// starting from the lowest sequence keeps the higher cards for later,
    /// since they may win in the other hand's stead.
    pub fn distinct_plays(
        &self,
        position: Position,
        cards: RankSet,
        contested: RankSet,
    ) -> Vec<Rank> {
        let missing = self.missing_ranks(position).union(contested);
        let unplayed = missing.union(position.north).union(position.south);
        let mut plays = Vec::new();
        // The play for the equivalent cards seen so far.
        let mut current: Option<Rank> = None;
        let mut previous: Option<Rank> = None;
        for card in cards.descending() {
            if let (Some(higher), Some(_)) = (previous, current) {
                let is_equivalent = RankSet::strictly_between(higher, card)
                    .intersection(missing)
                    .is_empty();
                let is_touching = RankSet::strictly_between(higher, card)
                    .intersection(unplayed)
                    .is_empty();
                if !is_equivalent {
                    plays.extend(current);
                    current = Some(card);
                } else if !is_touching {
                    // This card starts a lower sequence of equivalent cards,
                    // so it replaces the play so far.
                    current = Some(card);
                }
            } else {
                current = Some(card);
            }
            previous = Some(card);
        }
        plays.extend(current);
        plays
    }

    /// The cards in `cards` that take the same tricks as `card`: those with
    /// no defender card left between them and it, counting `contested` as
    /// left.
    pub fn equivalent_cards(
        &self,
        position: Position,
        cards: RankSet,
        card: Rank,
        contested: RankSet,
    ) -> RankSet {
        let blockers = self.missing_ranks(position).union(contested);
        run_around(cards, card, blockers)
    }

    /// The cards in `cards` that touch `card`, with no card at all left
    /// between them, counting `contested` as left.
    pub fn touching_cards(
        &self,
        position: Position,
        cards: RankSet,
        card: Rank,
        contested: RankSet,
    ) -> RankSet {
        let blockers = self
            .missing_ranks(position)
            .union(contested)
            .union(position.north)
            .union(position.south)
            .difference(cards);
        run_around(cards, card, blockers)
    }

    /// The frontier after a defender's turn in `trick`: second hand's, or
    /// else fourth hand's.
    pub fn defender_turn(&mut self, trick: Trick) -> Rc<Frontier> {
        self.within_trick(trick, Self::defender_turn_uncached)
    }

    /// The frontier after a defender's turn in `trick`, computed afresh.
    fn defender_turn_uncached(&mut self, trick: Trick) -> Rc<Frontier> {
        let live = self.live(trick.position);
        let mut combined = Frontier::single(&vec![live; self.level_count]);
        for (play, layouts) in self.defender_options(trick) {
            let child_trick = trick.with_defender_play(play);
            let child = if trick.second.is_none() {
                self.third_hand_turn(child_trick)
            } else {
                self.solve(child_trick.next_position(self.layouts))
            };
            combined = combined.combined_with(&child, live.difference(layouts));
        }
        Rc::new(combined)
    }

    /// The frontier after a lead, before second hand plays.
    fn after_lead(&mut self, trick: Trick) -> Rc<Frontier> {
        self.defender_turn(trick)
    }

    /// Each play the defender due to play in `trick` could make, with the
    /// layouts where that defender could make it.
    pub fn defender_options(
        &self,
        trick: Trick,
    ) -> Vec<(DefenderPlay, LayoutSet)> {
        let defender = trick.defender_to_play();
        let position = trick.position;
        let live = self.live(position);
        if position.shown_out[defender as usize] {
            return vec![(DefenderPlay::ShowOut, live)];
        }
        let played = position.played[defender as usize];
        let mut options = Vec::new();
        for group in 0..self.layouts.groups.len() {
            let layouts = live.intersection(self.layouts.at_least(
                defender,
                group,
                played.get(group) + 1,
            ));
            if !layouts.is_empty() {
                options.push((DefenderPlay::Group(group), layouts));
            }
        }
        let void = live
            .intersection(self.layouts.with_length(defender, played.total()));
        if !void.is_empty() {
            options.push((DefenderPlay::ShowOut, void));
        }
        options
    }

    /// Each play worth trying from the third hand in `trick`.
    pub fn third_hand_options(&self, trick: Trick) -> Vec<FollowPlay> {
        let cards = trick.position.hand(trick.leader.partner());
        if cards.is_empty() {
            return vec![FollowPlay::Discard];
        }
        let contested = match trick.second {
            Some(DefenderPlay::Group(group)) => {
                self.layouts.groups[group].ranks
            }
            _ => RankSet::EMPTY,
        };
        self.distinct_plays(trick.position, cards, contested)
            .into_iter()
            .map(FollowPlay::Card)
            .collect()
    }

    /// The frontier when the third hand is due to play in `trick`.
    pub fn third_hand_turn(&mut self, trick: Trick) -> Rc<Frontier> {
        self.within_trick(trick, Self::third_hand_turn_uncached)
    }

    /// The frontier when the third hand is due to play, computed afresh.
    fn third_hand_turn_uncached(&mut self, trick: Trick) -> Rc<Frontier> {
        let mut frontier = Frontier::new(self.level_count);
        for play in self.third_hand_options(trick) {
            let after = self.defender_turn(trick.with_third(play));
            frontier.merge(&after);
        }
        Rc::new(frontier)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cards::rank_for_symbol;
    use crate::layouts::DEAL_COUNT;
    use crate::notation::parse_problem;

    /// The chance, in percent, that the best strategy reaches the problem's
    /// target.
    fn best_percent(problem: &str) -> f64 {
        let problem = parse_problem(problem).expect("a valid problem");
        let layouts = Layouts::new(problem.combination);
        let mut solver = Solver::new(&layouts, problem.target, problem.target);
        let frontier = solver.solve(Position::start(&layouts));
        let best = frontier
            .results()
            .map(|result| layouts.weight(result[0]))
            .max()
            .expect("at least one result");
        100.0 * best as f64 / DEAL_COUNT as f64
    }

    fn ranks(cards: &str) -> RankSet {
        cards.chars().fold(RankSet::EMPTY, |set, symbol| {
            set.with(rank_for_symbol(symbol).expect("a rank symbol"))
        })
    }

    #[test]
    fn top_tricks_always_succeed() {
        assert_eq!(best_percent("AKQ-xxx@3"), 100.0);
    }

    #[test]
    fn a_simple_finesse_works_half_the_time() {
        assert!((best_percent("AQ-xx@2") - 50.0).abs() < 1e-9);
    }

    #[test]
    fn a_double_finesse_for_two_tricks() {
        // It fails only when both missing honors lie with East, a 13/26 ×
        // 12/25 = 24% chance.
        let percent = best_percent("AQT-xx@2");
        assert!((percent - 76.0).abs() < 1e-9, "{percent}");
    }

    #[test]
    fn distinct_plays_keep_one_card_per_equivalent_run() {
        let problem = parse_problem("AQTx-J9x@4").expect("a valid problem");
        let layouts = Layouts::new(problem.combination);
        let solver = Solver::new(&layouts, 4, 4);
        let start = Position::start(&layouts);

        // South's J and 9 are equivalent, with North's T between them; the 9,
        // the lower, stands for both.
        assert_eq!(
            solver.distinct_plays(start, ranks("J9"), RankSet::EMPTY),
            vec![rank_for_symbol('9').unwrap()]
        );
        // North's Q and T are equivalent too, with South's J between them.
        assert_eq!(
            solver.distinct_plays(
                start,
                layouts.combination.north,
                RankSet::EMPTY
            ),
            vec![
                rank_for_symbol('A').unwrap(),
                rank_for_symbol('T').unwrap(),
                layouts.combination.north.lowest().unwrap(),
            ]
        );
    }
}
