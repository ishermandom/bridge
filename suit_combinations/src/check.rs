// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Following a described line the way a reader would, to confirm that it
//! reaches the target wherever its strategy does.
//!
//! The reading is set out in `suit_combinations/spec.md` #checking-lines. In
//! short: each trick is played as its plan says, with the answers its step
//! states and those its name implies; each condition is read literally; and
//! the reader stops once the target is safe on sure winners.

use crate::cards::{Rank, RankSet, rank_symbol};
use crate::describe::{
    Answer, Condition, Line, Plan, Play, Step, TrickEnd, dedup, defender_name,
    implied_reply, restricted, step_words,
};
use crate::layout_set::LayoutSet;
use crate::layouts::{Defender, Layouts};
use crate::solver::{DefenderPlay, FollowPlay, Position, Solver, Trick};

/// Checks that `line`, played the way a reader would play it, reaches
/// `solver`'s lowest target in every layout of `required[0]`. The error says
/// where the line falls short, after the tricks that led there.
pub(crate) fn check(
    solver: &mut Solver,
    line: &Line,
    required: &[LayoutSet],
) -> Result<(), String> {
    let start = Position::start(solver.layouts);
    Reader { solver }.check_from(line, start, required)
}

/// A reader following a line, with the solver to tell what the defenders
/// might play.
struct Reader<'s, 'a> {
    solver: &'s mut Solver<'a>,
}

impl Reader<'_, '_> {
    /// `check` from `position`, with `required` cut down to the layouts
    /// still possible there.
    fn check_from(
        &mut self,
        line: &Line,
        position: Position,
        required: &[LayoutSet],
    ) -> Result<(), String> {
        if required[0].is_empty() || self.is_safe(position) {
            return Ok(());
        }
        match line {
            Line::Done => Err(format!(
                "the line stops with {} tricks won and the target not yet \
                 safe, in {} deals",
                position.tricks_won,
                self.solver.layouts.weight(required[0])
            )),
            Line::Split(_) => {
                Err("the line splits before any trick".to_string())
            }
            Line::Step(step, rest) => {
                self.check_trick(step, rest, position, required)
            }
        }
    }

    /// `card` if `cards` still holds it, or else one of `cards` that takes
    /// the same tricks, counting `contested` as left, as a reader would play
    /// in its stead; None if there's neither.
    fn card_or_equal(
        &self,
        position: Position,
        cards: RankSet,
        card: Rank,
        contested: RankSet,
    ) -> Option<Rank> {
        if cards.contains(card) {
            return Some(card);
        }
        // Count `card` as still held to find what takes the same tricks,
        // then play the lowest of the others.
        self.solver
            .equivalent_cards(position, cards.with(card), card, contested)
            .without(card)
            .lowest()
    }

    /// Whether the target is safe at `position` on sure winners, where the
    /// reader stops following the line and cashes them.
    fn is_safe(&self, position: Position) -> bool {
        self.solver.certain_tricks(position) >= self.solver.lowest_target
    }

    /// `check_from` for a trick played as `step` says, followed by `rest`.
    fn check_trick(
        &mut self,
        step: &Step,
        rest: &Line,
        position: Position,
        required: &[LayoutSet],
    ) -> Result<(), String> {
        let plan = step.plan;
        let words = step_words(step, self.solver.layouts);
        // "Cash" says no defender can beat the card. A line shortened by
        // merging parts could otherwise say so of a deal where a defender
        // still can.
        if let Play::Cash(card) = step.play {
            let missing = self.solver.missing_ranks(position);
            if let Some(high) = missing.highest().filter(|&high| high > card) {
                return Err(format!(
                    "\"{words}\" cashes a card the {} can still beat",
                    rank_symbol(high)
                ));
            }
        }
        let named_cards = named_cards(step.play);
        let leader_cards = position.hand(plan.leader);
        let lead = match plan.lead {
            // A card the words name must be in hand; one they leave unnamed
            // may be any of its equals.
            Some(card) if named_cards.contains(card) => {
                leader_cards.contains(card).then_some(card)
            }
            Some(card) => {
                self.card_or_equal(position, leader_cards, card, RankSet::EMPTY)
            }
            None => leader_cards.lowest(),
        }
        .ok_or_else(|| format!("\"{words}\" leads a card already played"))?;
        let named = Plan {
            leader: plan.leader,
            lead,
            third: plan.third,
        };
        let trick = Trick::led(position, plan.leader, lead);
        let at_stake: Vec<(DefenderPlay, LayoutSet)> = self
            .solver
            .defender_options(trick)
            .into_iter()
            .filter(|&(_, play_layouts)| {
                required
                    .iter()
                    .any(|set| !set.intersection(play_layouts).is_empty())
            })
            .collect();
        let second_defender = plan.leader.next_defender();
        let partner_cards = position.hand(plan.leader.partner());
        for &(second, play_layouts) in &at_stake {
            let required = restricted(required, play_layouts);
            if required[0].is_empty() {
                continue;
            }
            let stated = step.stated_answers.iter().find(|stated_answer| {
                stated_answer.defender == second_defender
                    && stated_answer.play == second
            });
            let contested = match second {
                DefenderPlay::Group(group) => {
                    self.solver.layouts.groups[group].ranks
                }
                DefenderPlay::ShowOut => RankSet::EMPTY,
            };
            // The reply the line calls for, stated or implied.
            let line_reply =
                match stated.map(|stated_answer| stated_answer.answer) {
                    None => implied_reply(
                        self.solver.layouts,
                        position,
                        named,
                        step.play,
                        second,
                    ),
                    Some(Answer::Low) => match partner_cards.lowest() {
                        Some(lowest) => FollowPlay::Card(lowest),
                        None => FollowPlay::Discard,
                    },
                    Some(Answer::Card(card)) => FollowPlay::Card(card),
                };
            let is_card_named = stated.is_some_and(|stated_answer| {
                stated_answer.answer != Answer::Low
            }) || matches!(line_reply,
                    FollowPlay::Card(card) if named_cards.contains(card));
            let reply = match line_reply {
                FollowPlay::Card(card) if is_card_named => {
                    if !partner_cards.contains(card) {
                        return Err(format!(
                            "\"{words}\" plays a card already played"
                        ));
                    }
                    FollowPlay::Card(card)
                }
                FollowPlay::Card(card) => FollowPlay::Card(
                    self.card_or_equal(
                        position,
                        partner_cards,
                        card,
                        contested,
                    )
                    .ok_or_else(|| {
                        format!("\"{words}\" plays a card already played")
                    })?,
                ),
                FollowPlay::Discard => FollowPlay::Discard,
            };
            let played = trick.with_defender_play(second).with_third(reply);
            for (fourth, _) in self.solver.defender_options(played) {
                let done = played.with_defender_play(fourth);
                let next = done.next_position(self.solver.layouts);
                let next_required =
                    restricted(&required, self.solver.possible_layouts(next));
                if next_required[0].is_empty() {
                    continue;
                }
                let end = Ending {
                    second_defender,
                    second,
                    fourth_defender: plan.leader.last_defender(),
                    fourth,
                    declarer_won: done.declarer_wins(self.solver.layouts),
                };
                // A split, nested or not, routes the ending to the one part
                // whose condition it meets, or else to an "Otherwise".
                let mut next_line = rest;
                while let Line::Split(parts) = next_line {
                    let mut lines: Vec<&Line> = dedup(
                        parts
                            .iter()
                            .filter(|part| end.meets(&part.condition))
                            .map(|part| &part.line),
                    );
                    if lines.is_empty() {
                        lines.extend(
                            parts
                                .iter()
                                .filter(|part| {
                                    part.condition == Condition::Otherwise
                                })
                                .map(|part| &part.line),
                        );
                    }
                    next_line = match lines.as_slice() {
                        [line] => line,
                        [] if self.is_safe(next) => &Line::Done,
                        [] => {
                            return Err(format!(
                                "after \"{words}\", no condition covers {}",
                                end.words(self.solver.layouts)
                            ));
                        }
                        _ => {
                            return Err(format!(
                                "after \"{words}\", two conditions with \
                                 different lines cover {}",
                                end.words(self.solver.layouts)
                            ));
                        }
                    };
                }
                self.check_from(next_line, next, &next_required).map_err(
                    |error| {
                        // The trick, in play order, then what failed after it.
                        let label = trick_label(
                            self.solver.layouts,
                            lead,
                            second,
                            reply,
                            fourth,
                        );
                        format!("[{label}] {error}")
                    },
                )?;
            }
        }
        Ok(())
    }
}

/// A trick's cards in play order, such as "5 K A -", with "-" for a
/// show-out or a discard.
fn trick_label(
    layouts: &Layouts,
    lead: Rank,
    second: DefenderPlay,
    reply: FollowPlay,
    fourth: DefenderPlay,
) -> String {
    let reply = match reply {
        FollowPlay::Card(card) => rank_symbol(card).to_string(),
        FollowPlay::Discard => "-".to_string(),
    };
    format!(
        "{} {} {} {}",
        rank_symbol(lead),
        defender_play_symbol(layouts, second),
        reply,
        defender_play_symbol(layouts, fourth)
    )
}

/// A defender's play as one symbol: the top card of its group, or "-" for a
/// show-out.
fn defender_play_symbol(layouts: &Layouts, play: DefenderPlay) -> String {
    match play {
        DefenderPlay::Group(group) => {
            rank_symbol(layouts.groups[group].top()).to_string()
        }
        DefenderPlay::ShowOut => "-".to_string(),
    }
}

/// The cards `play`'s words name, which a reader must hold as named; the
/// low cards they leave unnamed may be any of their equals.
fn named_cards(play: Play) -> RankSet {
    match play {
        Play::Cash(card)
        | Play::Toward { lead: None, card }
        | Play::Run(card)
        | Play::Lead(card) => RankSet::single(card),
        Play::Toward {
            lead: Some(lead),
            card,
        } => RankSet::single(lead).with(card),
        Play::Other { lead, third } => RankSet::single(lead).with(third),
        Play::LeadLow(_) | Play::Duck(_) => RankSet::EMPTY,
    }
}

/// How a trick actually ended, for matching against a line's conditions.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Ending {
    second_defender: Defender,
    second: DefenderPlay,
    fourth_defender: Defender,
    fourth: DefenderPlay,
    declarer_won: bool,
}

impl Ending {
    /// The ending a branch records, or None for one that doesn't say what
    /// second hand played.
    pub(crate) fn of(end: TrickEnd) -> Option<Ending> {
        let (second_defender, second) = end.second?;
        Some(Ending {
            second_defender,
            second,
            fourth_defender: end.defender,
            fourth: end.play,
            declarer_won: end.declarer_won,
        })
    }

    /// The ending in words for an error message, such as "West K, East -,
    /// declarer wins", with "-" for a show-out.
    fn words(&self, layouts: &Layouts) -> String {
        let winner = if self.declarer_won {
            "declarer wins"
        } else {
            "the defenders win"
        };
        format!(
            "{} {}, {} {}, {winner}",
            defender_name(self.second_defender),
            defender_play_symbol(layouts, self.second),
            defender_name(self.fourth_defender),
            defender_play_symbol(layouts, self.fourth)
        )
    }

    /// Whether this ending meets `condition`, read literally: a condition
    /// that names no second-hand card holds whatever second hand played.
    /// "Otherwise" isn't met on its own; it takes what no other part does.
    pub(crate) fn meets(&self, condition: &Condition) -> bool {
        match condition {
            Condition::Wins => self.declarer_won,
            Condition::Loses => !self.declarer_won,
            Condition::Ended(ends) => ends.iter().any(|end| self.is(end)),
            Condition::Otherwise => false,
        }
    }

    /// Whether this ending is one `end` names.
    fn is(&self, end: &TrickEnd) -> bool {
        let is_second = |(defender, play): (Defender, DefenderPlay)| {
            (defender, play) == (self.second_defender, self.second)
        };
        if end.defender == self.second_defender && end.second.is_none() {
            // An ending merged into second hand's play names second hand as
            // its defender and no second play; it holds whatever fourth hand
            // played and whoever won the trick.
            return end.play == self.second;
        }
        end.second.is_none_or(is_second)
            && end.defender == self.fourth_defender
            && end.play == self.fourth
            && end.declarer_won == self.declarer_won
    }
}
