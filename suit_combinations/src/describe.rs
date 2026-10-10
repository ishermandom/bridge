// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Putting a best strategy into words, trick by trick.
//!
//! The approach is set out in `suit_combinations/spec.md` #describing-lines.
//! In short: each trick is described by the card led and the card played
//! from the other hand when second hand plays low, such as "low to the Q".
//! The next trick follows with "then" when it is the same whatever happened,
//! and otherwise splits on how the trick went. The description stops once
//! the rest is cashing winners, or once nothing can still succeed.

use crate::cards::{Rank, RankSet, rank_symbol};
use crate::layout_set::LayoutSet;
use crate::layouts::{Defender, Layouts};
use crate::solver::{
    DefenderPlay, FollowPlay, Frontier, Hand, Position, Solver, Trick,
};

/// One trick of a line, as the description names it.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Play {
    /// Win the trick with a card no defender can beat.
    Cash(Rank),
    /// Lead toward a card and play it if second hand plays low. `lead` names
    /// the card led when it isn't the leader's lowest.
    Toward { lead: Option<Rank>, card: Rank },
    /// Lead a card and play low from the other hand if second hand plays
    /// low.
    Run(Rank),
    /// Lead a card with nothing to play from the other hand.
    Lead(Rank),
    /// Play low from both hands, giving up the trick.
    Duck(Hand),
    /// Lead one card and play another, fitting none of the above.
    Other { lead: Rank, third: Rank },
}

impl Play {
    /// The play in words, starting in lowercase.
    pub fn words(self) -> String {
        let name = |rank: Rank| format!("the {}", rank_symbol(rank));
        match self {
            Play::Cash(card) => format!("cash {}", name(card)),
            Play::Toward { lead: None, card } => {
                format!("low to {}", name(card))
            }
            Play::Toward {
                lead: Some(lead),
                card,
            } => {
                format!("lead {} to {}", name(lead), name(card))
            }
            Play::Run(card) => format!("run {}", name(card)),
            Play::Lead(card) => format!("lead {}", name(card)),
            Play::Duck(_) => "duck a round".to_string(),
            Play::Other { lead, third } => {
                format!("lead {} and play {}", name(lead), name(third))
            }
        }
    }
}

/// How the previous trick went, as a condition on what follows.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Condition {
    /// Declarer won the trick.
    Wins,
    /// The defenders won the trick.
    Loses,
    /// The trick ended in one of these ways.
    Ended(Vec<TrickEnd>),
}

/// How a trick ended: who won it, and the play that set it apart.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct TrickEnd {
    /// Whether declarer won the trick. For an ending merged by
    /// `collapsed_ends`, false means second hand's card took the trick, and
    /// true means the condition says only what second hand played, whoever
    /// won.
    pub declarer_won: bool,
    /// The defender whose play set this ending apart: the last to play, or
    /// second hand when it showed out.
    pub defender: Defender,
    pub play: DefenderPlay,
}

/// A line of play.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Line {
    /// Nothing left to decide: the tricks still wanted come from winners, or
    /// can't come at all.
    Done,
    /// A trick's play, then the rest of the line.
    Play(Play, Box<Line>),
    /// Different continuations, depending on how the last trick went.
    Split(Vec<(Condition, Line)>),
}

impl Line {
    /// The tricks the line describes along its first path, in order.
    pub fn first_path(&self) -> Vec<Play> {
        let mut plays = Vec::new();
        let mut line = self;
        loop {
            match line {
                Line::Done => return plays,
                Line::Play(play, rest) => {
                    plays.push(*play);
                    line = rest;
                }
                Line::Split(parts) => line = &parts[0].1,
            }
        }
    }
}

/// The line in words, such as "Low to the T, then low to the Q".
pub fn line_words(line: &Line, layouts: &Layouts) -> String {
    capitalize(&lowercase_words(line, layouts))
}

/// The line in words, starting in lowercase.
fn lowercase_words(line: &Line, layouts: &Layouts) -> String {
    match line {
        Line::Done => "cash the winners".to_string(),
        Line::Play(play, rest) => match rest.as_ref() {
            Line::Done => play.words(),
            Line::Play(..) => {
                format!(
                    "{}, then {}",
                    play.words(),
                    lowercase_words(rest, layouts)
                )
            }
            Line::Split(_) => {
                format!("{}. {}", play.words(), lowercase_words(rest, layouts))
            }
        },
        Line::Split(parts) => parts
            .iter()
            .map(|(condition, rest)| {
                let words = lowercase_words(rest, layouts);
                let sentence = format!(
                    "{}, {}",
                    condition_words(condition, layouts),
                    words
                );
                // A nested split already ends in a full stop.
                if sentence.ends_with('.') {
                    sentence
                } else {
                    format!("{sentence}.")
                }
            })
            .map(|sentence| capitalize(&sentence))
            .collect::<Vec<_>>()
            .join(" "),
    }
}

/// A condition in words, such as "If that wins".
fn condition_words(condition: &Condition, layouts: &Layouts) -> String {
    let ends = match condition {
        Condition::Wins => return "If that wins".to_string(),
        Condition::Loses => return "If it loses".to_string(),
        Condition::Ended(ends) => ends,
    };
    let defender_name = |defender: Defender| match defender {
        Defender::West => "West",
        Defender::East => "East",
    };
    // When one defender plays a different card each time, name the cards
    // together: "If East plays the T or a low card".
    let first = ends[0];
    let is_one_defender_following = ends.iter().all(|end| {
        end.defender == first.defender
            && end.declarer_won == first.declarer_won
            && matches!(end.play, DefenderPlay::Group(_))
    });
    if is_one_defender_following && first.declarer_won {
        let cards: Vec<String> = ends
            .iter()
            .map(|end| match end.play {
                DefenderPlay::Group(group) => group_words(layouts, group),
                DefenderPlay::ShowOut => unreachable!("checked above"),
            })
            .collect();
        return format!(
            "If {} plays {}",
            defender_name(first.defender),
            cards.join(" or ")
        );
    }
    let phrases: Vec<String> = ends
        .iter()
        .map(|end| {
            let defender = defender_name(end.defender);
            match (end.declarer_won, end.play) {
                (_, DefenderPlay::ShowOut) => format!("{defender} shows out"),
                (false, DefenderPlay::Group(group))
                    if layouts.groups[group].size() == 1 =>
                {
                    format!(
                        "it loses to the {}",
                        rank_symbol(layouts.groups[group].top())
                    )
                }
                (false, _) => format!("{defender} wins"),
                (true, DefenderPlay::Group(group)) => {
                    format!("{defender} plays {}", group_words(layouts, group))
                }
            }
        })
        .collect();
    format!("If {}", phrases.join(" or "))
}

/// A defender's group in words, such as "the K" or "a low card".
pub fn group_words(layouts: &Layouts, group: usize) -> String {
    let ranks = layouts.groups[group].ranks;
    if ranks.len() == 1 {
        return format!("the {}", rank_symbol(layouts.groups[group].top()));
    }
    if group + 1 == layouts.groups.len() {
        return "a low card".to_string();
    }
    let names: Vec<String> = ranks
        .descending()
        .map(|rank| rank_symbol(rank).to_string())
        .collect();
    format!("one of the {}", names.join(", "))
}

/// `text` with its first letter capitalized.
fn capitalize(text: &str) -> String {
    let mut characters = text.chars();
    match characters.next() {
        Some(first) => first.to_uppercase().chain(characters).collect(),
        None => String::new(),
    }
}

/// One concrete way to play a trick: the lead, and the third hand's card when
/// second hand plays below the card declarer means to win with.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct Plan {
    leader: Hand,
    lead: Rank,
    third: FollowPlay,
}

impl Plan {
    /// The card declarer means to win the trick with.
    fn winner(self) -> Rank {
        match self.third {
            FollowPlay::Card(third) => third.max(self.lead),
            FollowPlay::Discard => self.lead,
        }
    }

    /// The hand holding `winner()`.
    fn winning_hand(self) -> Hand {
        match self.third {
            FollowPlay::Card(third) if third > self.lead => {
                self.leader.partner()
            }
            _ => self.leader,
        }
    }
}

/// What a plan leads, for matching plans across branches: a low card, or a
/// particular one.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
enum LeadKey {
    Low,
    Card(Rank),
}

/// A plan as the description matches it across branches: plans with the same
/// key in two branches follow the same instruction.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
struct PlanKey {
    leader: Hand,
    lead: LeadKey,
    third: FollowPlay,
}

/// A plan that achieves what a branch requires.
#[derive(Clone, Copy, Debug)]
struct Candidate {
    key: PlanKey,
    /// What the plan does, as named in this branch.
    play: Play,
    plan: Plan,
    /// The second hand's play and declarer's reply that the description
    /// follows from here.
    main_line: (DefenderPlay, FollowPlay),
    /// The entries the plan costs: one when it leads from the hand that
    /// didn't win the last trick.
    entries: u32,
    /// Ranks the candidate among ties, lowest first: the lower set of
    /// equivalent cards first, then the lower run of touching cards, then
    /// the higher card within a run.
    preference: (Rank, Rank, i8),
}

/// One way the play so far might have gone, with what the strategy must
/// still achieve.
#[derive(Clone, Debug)]
struct Branch {
    /// The position at the start of the next trick.
    position: Position,
    /// For each target, the layouts where the strategy must still reach it.
    required: Vec<LayoutSet>,
    /// The hand that won the last trick, when declarer won it.
    hand_in: Option<Hand>,
    /// How the last trick ended, if there was one.
    ended: Option<TrickEnd>,
}

/// How much a description costs, compared in order: the entries it needs,
/// then the tricks it spells out.
type Cost = (u32, u32);

/// How many of the candidate plays common to every branch the description
/// tries at each trick, in order of preference. Each one tried describes the
/// rest of the line afresh, so the limit keeps long lines quick.
const PLAYS_TRIED: usize = 4;

/// Describes strategies using a solver's frontiers.
pub struct Describer<'s, 'a> {
    solver: &'s mut Solver<'a>,
}

impl<'s, 'a> Describer<'s, 'a> {
    pub fn new(solver: &'s mut Solver<'a>) -> Describer<'s, 'a> {
        Describer { solver }
    }

    /// A line achieving `required` from the start, where `required` holds,
    /// for each of the solver's targets, the layouts where the line must
    /// reach it.
    pub fn describe(&mut self, required: &[LayoutSet]) -> Line {
        let start = Branch {
            position: Position::start(self.solver.layouts),
            required: required.to_vec(),
            // South is on lead at the start.
            hand_in: Some(Hand::South),
            ended: None,
        };
        self.describe_branches(vec![start]).1
    }

    /// The cheapest line covering every branch whose target is still at
    /// stake.
    ///
    /// A branch whose target is already safe but which can still make
    /// overtricks goes along with a play the other branches choose, when that
    /// play suits it, and is dropped otherwise: overtricks shape the line only
    /// where they come for free.
    fn describe_branches(&mut self, branches: Vec<Branch>) -> (Cost, Line) {
        let mut hard = Vec::new();
        let mut soft = Vec::new();
        for branch in branches {
            match self.urgency(&branch) {
                Urgency::Target => hard.push(branch),
                Urgency::Overtricks => soft.push(branch),
                Urgency::Settled => {}
            }
        }
        if hard.is_empty() {
            return ((0, 0), Line::Done);
        }

        let hard_options: Vec<Vec<Candidate>> =
            hard.iter().map(|branch| self.candidates(branch)).collect();
        let soft_options: Vec<Vec<Candidate>> =
            soft.iter().map(|branch| self.candidates(branch)).collect();
        let common = common_keys(&hard_options);

        let mut best: Option<(Cost, Line)> = None;
        for key in common.into_iter().take(PLAYS_TRIED) {
            let mut entries = 0;
            let mut next = Vec::new();
            let mut plays = Vec::new();
            let followed = hard
                .iter()
                .zip(&hard_options)
                .chain(soft.iter().zip(&soft_options));
            for (branch, each) in followed {
                let Some(candidate) = each
                    .iter()
                    .filter(|candidate| candidate.key == key)
                    .min_by_key(|candidate| candidate.entries)
                else {
                    continue;
                };
                entries += candidate.entries;
                plays.push(candidate.play);
                next.extend(self.after(branch, candidate));
            }
            // A play that only cashes a winner in one branch may be a finesse
            // in another, and the finesse is the one worth naming.
            let play = plays
                .iter()
                .copied()
                .find(|play| !matches!(play, Play::Cash(_)))
                .unwrap_or(plays[0]);
            let (rest_cost, rest) = self.describe_branches(next);
            let cost = (entries + rest_cost.0, 1 + rest_cost.1);
            if best.as_ref().is_none_or(|(best_cost, _)| cost < *best_cost) {
                best = Some((cost, Line::Play(play, Box::new(rest))));
            }
        }
        if let Some(best) = best {
            return best;
        }
        self.split(hard, &hard_options, soft)
    }

    /// Separate lines for branches that no single play suits, grouping
    /// together the branches that share a play.
    fn split(
        &mut self,
        hard: Vec<Branch>,
        options: &[Vec<Candidate>],
        soft: Vec<Branch>,
    ) -> (Cost, Line) {
        // Each group takes the play that suits the most branches left.
        let mut remaining: Vec<usize> = (0..hard.len()).collect();
        let mut groups: Vec<Vec<usize>> = Vec::new();
        while !remaining.is_empty() {
            let mut best_key: Option<(usize, (Rank, Rank, i8), PlanKey)> = None;
            for &index in &remaining {
                for candidate in &options[index] {
                    let count = remaining
                        .iter()
                        .filter(|&&other| {
                            options[other]
                                .iter()
                                .any(|each| each.key == candidate.key)
                        })
                        .count();
                    let is_better =
                        best_key.is_none_or(|(best_count, preference, _)| {
                            count > best_count
                                || (count == best_count
                                    && candidate.preference < preference)
                        });
                    if is_better {
                        best_key =
                            Some((count, candidate.preference, candidate.key));
                    }
                }
            }
            let (_, _, key) = best_key.expect("every branch has a valid play");
            let (group, rest): (Vec<usize>, Vec<usize>) =
                remaining.iter().partition(|&&index| {
                    options[index].iter().any(|each| each.key == key)
                });
            groups.push(group);
            remaining = rest;
        }

        let all_won: Vec<usize> = (0..hard.len())
            .filter(|&index| {
                hard[index].ended.is_some_and(|end| end.declarer_won)
            })
            .collect();
        let mut cost = (0, 0);
        let mut parts = Vec::new();
        for group in groups {
            let ends: Vec<TrickEnd> = dedup(group.iter().map(|&index| {
                hard[index].ended.expect("a split follows a trick")
            }));
            let condition = if groups_by_outcome(&group, &all_won, hard.len()) {
                if group == all_won {
                    Condition::Wins
                } else {
                    Condition::Loses
                }
            } else {
                Condition::Ended(ends.clone())
            };
            let mut branches: Vec<Branch> =
                group.iter().map(|&index| hard[index].clone()).collect();
            // A branch only making overtricks follows the group that ended
            // its trick the same way.
            branches.extend(
                soft.iter()
                    .filter(|branch| {
                        branch.ended.is_some_and(|end| ends.contains(&end))
                    })
                    .cloned(),
            );
            let (part_cost, line) = self.describe_branches(branches);
            cost = (cost.0 + part_cost.0, cost.1 + part_cost.1);
            parts.push((condition, line));
        }
        (cost, Line::Split(parts))
    }

    /// What the branch still has at stake: its target, only overtricks, or
    /// nothing, once its sure winners count.
    fn urgency(&self, branch: &Branch) -> Urgency {
        let position = branch.position;
        let rounds_left = position.north.len().max(position.south.len());
        let certain = position.tricks_won
            + self.solver.sure_tricks(position).min(rounds_left);
        let pending = |level: usize| {
            // `level` indexes the solver's targets, which fit in a `u8`.
            let target = self.solver.lowest_target + level as u8;
            !branch.required[level].is_empty() && target > certain
        };
        if pending(0) {
            Urgency::Target
        } else if (1..branch.required.len()).any(pending) {
            Urgency::Overtricks
        } else {
            Urgency::Settled
        }
    }

    /// Every plan that can still achieve the branch's requirement.
    fn candidates(&mut self, branch: &Branch) -> Vec<Candidate> {
        let position = branch.position;
        let live = self.solver.live(position);
        let level_count = self.solver.level_count;
        let mut candidates = Vec::new();
        for (leader, lead) in self.solver.leads(position) {
            let trick = Trick::led(position, leader, lead);
            let options = self.solver.defender_options(trick);

            // Plans whose third card answers one of second hand's plays: the
            // highest that stays below the card declarer means to win with.
            for &(low, low_layouts) in &options {
                let low_trick = trick.with_defender_play(low);
                let thirds = self.solver.third_hand_options(low_trick);
                let mut others = None;
                for &third in &thirds {
                    let plan = Plan {
                        leader,
                        lead,
                        third,
                    };
                    if self.low_play(&options, plan) != Some(low) {
                        continue;
                    }
                    let others = others.get_or_insert_with(|| {
                        let mut combined =
                            Frontier::single(&vec![live; level_count]);
                        for &(play, layouts) in &options {
                            if play != low {
                                let child = self.solver.third_hand_turn(
                                    trick.with_defender_play(play),
                                );
                                combined = combined.combined_with(
                                    &child,
                                    live.difference(layouts),
                                );
                            }
                        }
                        combined
                    });
                    let child =
                        self.solver.defender_turn(low_trick.with_third(third));
                    let combined = others
                        .combined_with(&child, live.difference(low_layouts));
                    if combined.achieves(&branch.required) {
                        self.add_candidates(
                            &mut candidates,
                            branch,
                            plan,
                            (low, third),
                            low,
                        );
                    }
                }
            }

            // Plans that second hand can never play below: declarer answers
            // whatever comes freely, so only the lead is fixed.
            let after_lead = self.solver.after_lead(trick);
            if !after_lead.achieves(&branch.required) {
                continue;
            }
            for third in self.solver.third_hand_options(trick) {
                let plan = Plan {
                    leader,
                    lead,
                    third,
                };
                if self.low_play(&options, plan).is_some() {
                    continue;
                }
                if let Some(main_line) =
                    self.free_main_line(branch, trick, &options, third)
                {
                    self.add_candidates(
                        &mut candidates,
                        branch,
                        plan,
                        main_line,
                        main_line.0,
                    );
                }
            }
        }
        candidates
    }

    /// Second hand's low play against `plan`: its lowest play below the card
    /// declarer means to win with. None when second hand has no such play,
    /// which leaves declarer's reply free.
    fn low_play(
        &self,
        options: &[(DefenderPlay, LayoutSet)],
        plan: Plan,
    ) -> Option<DefenderPlay> {
        let groups = &self.solver.layouts.groups;
        let below: Vec<DefenderPlay> = options
            .iter()
            .map(|&(play, _)| play)
            .filter(|play| match play {
                DefenderPlay::Group(group) => {
                    groups[*group].top() < plan.winner()
                }
                DefenderPlay::ShowOut => false,
            })
            .collect();
        if let Some(&lowest) = below.last() {
            return Some(lowest);
        }
        // A defender with no card at all can only show out.
        match options {
            [(DefenderPlay::ShowOut, _)] => Some(DefenderPlay::ShowOut),
            _ => None,
        }
    }

    /// When second hand can't play low, the play the description follows
    /// instead, second hand's lowest, paired with a reply that still meets
    /// the branch's requirement: `planned` when that works. `options` runs
    /// from the highest group down, so the lowest play is its last group.
    fn free_main_line(
        &mut self,
        branch: &Branch,
        trick: Trick,
        options: &[(DefenderPlay, LayoutSet)],
        planned: FollowPlay,
    ) -> Option<(DefenderPlay, FollowPlay)> {
        let &(play, layouts) = options
            .iter()
            .rev()
            .find(|(play, _)| matches!(play, DefenderPlay::Group(_)))?;
        let required: Vec<LayoutSet> = branch
            .required
            .iter()
            .map(|set| set.intersection(layouts))
            .collect();
        let played = trick.with_defender_play(play);
        let mut replies = self.solver.third_hand_options(played);
        // Equivalent cards may stand in for the planned one.
        if let Some(index) = replies.iter().position(|&reply| reply == planned)
        {
            replies.swap(0, index);
        }
        for third in replies {
            if self
                .solver
                .defender_turn(played.with_third(third))
                .achieves(&required)
            {
                return Some((play, third));
            }
        }
        None
    }

    /// Add the candidates for `plan`, a plan valid in `branch`, under each
    /// name its equivalent cards give it.
    ///
    /// The card meant to win the trick may be any of its equivalents, since
    /// a sibling branch may only offer one of them; a card played under it
    /// is always the lowest of its equivalents, keeping the higher ones.
    fn add_candidates(
        &self,
        candidates: &mut Vec<Candidate>,
        branch: &Branch,
        plan: Plan,
        main_line: (DefenderPlay, FollowPlay),
        second: DefenderPlay,
    ) {
        let position = branch.position;
        let contested = match second {
            DefenderPlay::Group(group) => {
                self.solver.layouts.groups[group].ranks
            }
            DefenderPlay::ShowOut => RankSet::EMPTY,
        };
        let leader_cards = position.hand(plan.leader);
        let partner_cards = position.hand(plan.leader.partner());
        let lead_group = self.solver.equivalent_cards(
            position,
            leader_cards,
            plan.lead,
            RankSet::EMPTY,
        );
        let lowest_lead = self
            .solver
            .distinct_plays(position, leader_cards, RankSet::EMPTY)
            .last()
            .copied();
        let leads_low = lowest_lead
            .is_some_and(|lowest| lead_group.contains(lowest))
            && plan.winning_hand() != plan.leader;
        let third_group = match plan.third {
            FollowPlay::Card(third) => self.solver.equivalent_cards(
                position,
                partner_cards,
                third,
                contested,
            ),
            FollowPlay::Discard => RankSet::EMPTY,
        };
        let lowest = |set: RankSet| set.lowest().expect("a nonempty set");

        let (leads, thirds): (Vec<Rank>, Vec<FollowPlay>) = if plan
            .winning_hand()
            == plan.leader
        {
            let third = match plan.third {
                FollowPlay::Card(_) => FollowPlay::Card(lowest(third_group)),
                FollowPlay::Discard => FollowPlay::Discard,
            };
            (lead_group.descending().collect(), vec![third])
        } else {
            (
                vec![lowest(lead_group)],
                third_group.descending().map(FollowPlay::Card).collect(),
            )
        };
        let entries =
            u32::from(branch.hand_in.is_some_and(|hand| hand != plan.leader));
        for &lead in &leads {
            for &third in &thirds {
                let named = Plan {
                    lead,
                    third,
                    ..plan
                };
                let key = PlanKey {
                    leader: plan.leader,
                    lead: if leads_low {
                        LeadKey::Low
                    } else {
                        LeadKey::Card(lead)
                    },
                    third,
                };
                let main_line = if main_line.1 == plan.third {
                    (main_line.0, third)
                } else {
                    main_line
                };
                let winner = named.winner();
                let winner_cards = if named.winning_hand() == plan.leader {
                    leader_cards
                } else {
                    partner_cards
                };
                let preference = if matches!(
                    self.classify(position, named, leads_low),
                    Play::Duck(_)
                ) {
                    // Giving up a trick is the last resort among ties.
                    (Rank::MAX, Rank::MAX, 0)
                } else {
                    (
                        lowest(self.solver.equivalent_cards(
                            position,
                            winner_cards,
                            winner,
                            contested,
                        )),
                        lowest(self.solver.touching_cards(
                            position,
                            winner_cards,
                            winner,
                            contested,
                        )),
                        // Ranks run below 13.
                        -(winner as i8),
                    )
                };
                candidates.push(Candidate {
                    key,
                    play: self.classify(position, named, leads_low),
                    plan: named,
                    main_line,
                    entries,
                    preference,
                });
            }
        }
    }

    /// What `plan` does, as the description names it.
    fn classify(
        &self,
        position: Position,
        plan: Plan,
        leads_low: bool,
    ) -> Play {
        let missing = self.solver.missing_ranks(position);
        let is_top =
            |card: Rank| missing.highest().is_none_or(|high| card > high);
        let FollowPlay::Card(third) = plan.third else {
            return if is_top(plan.lead) {
                Play::Cash(plan.lead)
            } else {
                Play::Lead(plan.lead)
            };
        };
        if missing
            .lowest()
            .is_some_and(|lowest| plan.winner() < lowest)
        {
            return Play::Duck(plan.leader);
        }
        if third > plan.lead {
            if is_top(third) && leads_low {
                return Play::Cash(third);
            }
            let lead = if leads_low { None } else { Some(plan.lead) };
            return Play::Toward { lead, card: third };
        }
        if is_top(plan.lead) {
            return Play::Cash(plan.lead);
        }
        let partner_cards = position.hand(plan.leader.partner());
        let is_partner_low = partner_cards.lowest().is_some_and(|lowest| {
            self.solver
                .equivalent_cards(
                    position,
                    partner_cards,
                    lowest,
                    RankSet::EMPTY,
                )
                .contains(third)
        });
        if is_partner_low {
            Play::Run(plan.lead)
        } else {
            Play::Other {
                lead: plan.lead,
                third,
            }
        }
    }

    /// The branches after `candidate`'s trick: one for each play fourth hand
    /// might make after the main line, plus those after second hand shows
    /// out.
    fn after(&mut self, branch: &Branch, candidate: &Candidate) -> Vec<Branch> {
        let plan = candidate.plan;
        let led = Trick::led(branch.position, plan.leader, plan.lead);
        let (second, third) = candidate.main_line;
        let mut branches = self.after_second(branch, led, second, third, false);

        // A show-out tells declarer where the rest of the suit is, so what
        // follows it is worth describing too.
        let options = self.solver.defender_options(led);
        let show_out = options
            .iter()
            .find(|(play, _)| *play == DefenderPlay::ShowOut);
        if let Some(&(play, layouts)) = show_out
            && play != second
        {
            let required: Vec<LayoutSet> = branch
                .required
                .iter()
                .map(|set| set.intersection(layouts))
                .collect();
            let shown = led.with_defender_play(play);
            for reply in self.solver.third_hand_options(shown) {
                let after_reply =
                    self.solver.defender_turn(shown.with_third(reply));
                if after_reply.achieves(&required) {
                    branches.extend(
                        self.after_second(branch, led, play, reply, true),
                    );
                    break;
                }
            }
        }
        branches
    }

    /// The branches after second hand plays `second` and the third hand
    /// `third`, one for each play fourth hand might make. `second_set_apart`
    /// says whether second hand's play, rather than fourth hand's, is what
    /// sets these branches apart.
    fn after_second(
        &mut self,
        branch: &Branch,
        led: Trick,
        second: DefenderPlay,
        third: FollowPlay,
        second_set_apart: bool,
    ) -> Vec<Branch> {
        let trick = led.with_defender_play(second).with_third(third);
        let layouts = self.solver.layouts;
        let mut branches = Vec::new();
        for (play, _) in self.solver.defender_options(trick) {
            let done = trick.with_defender_play(play);
            let position = done.next_position(layouts);
            let live = self.solver.live(position);
            let required = branch
                .required
                .iter()
                .map(|layouts| layouts.intersection(live))
                .collect();
            let declarer_won = done.declarer_wins(layouts);
            let winning_hand = match third {
                FollowPlay::Card(card) if card > led.lead => {
                    led.leader.partner()
                }
                _ => led.leader,
            };
            let (defender, setting_apart) = if second_set_apart {
                (led.leader.next_defender(), second)
            } else {
                (led.leader.last_defender(), play)
            };
            branches.push(Branch {
                position,
                required,
                hand_in: declarer_won.then_some(winning_hand),
                ended: Some(TrickEnd {
                    declarer_won,
                    defender,
                    play: setting_apart,
                }),
            });
        }
        branches
    }
}

/// What a branch still has at stake.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Urgency {
    /// The target itself.
    Target,
    /// Only overtricks.
    Overtricks,
    /// Nothing: its sure winners cover everything it could still make.
    Settled,
}

/// The plan keys valid in every branch, in order of preference.
fn common_keys(options: &[Vec<Candidate>]) -> Vec<PlanKey> {
    let mut ordered = options[0].clone();
    ordered.sort_by_key(|candidate| candidate.preference);
    let mut common: Vec<PlanKey> = Vec::new();
    for candidate in &ordered {
        let is_everywhere = options[1..]
            .iter()
            .all(|each| each.iter().any(|other| other.key == candidate.key));
        if is_everywhere && !common.contains(&candidate.key) {
            common.push(candidate.key);
        }
    }
    common
}

/// Whether `group` is exactly the branches that won, or exactly those that
/// lost, of `count` branches of which those in `won` won, with some of each.
fn groups_by_outcome(group: &[usize], won: &[usize], count: usize) -> bool {
    let has_both = !won.is_empty() && won.len() < count;
    let lost: Vec<usize> =
        (0..count).filter(|index| !won.contains(index)).collect();
    has_both && (group == won || group == lost)
}

/// `items` with repeats removed, keeping the first of each.
fn dedup<T: PartialEq>(items: impl Iterator<Item = T>) -> Vec<T> {
    let mut unique = Vec::new();
    for item in items {
        if !unique.contains(&item) {
            unique.push(item);
        }
    }
    unique
}
