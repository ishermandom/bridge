// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Putting a best strategy into words, trick by trick.
//!
//! The approach is set out in `suit_combinations/spec.md` #describing-lines.
//! In short: each trick is named by the card led and the card the other hand
//! plays when second hand plays low, such as "low to the Q". Every other card
//! second hand might play gets an answer, either one the name implies or one
//! stated beside it. The next trick follows with "then" when it is the same
//! whatever happened, and otherwise splits on how the trick went. The
//! description stops once the rest is cashing winners, or once nothing can
//! still succeed. `crate::check` reads a line back the way a reader would, to
//! confirm it's complete.

use crate::cards::{Rank, RankSet, rank_symbol};
use crate::check;
use crate::layout_set::LayoutSet;
use crate::layouts::{Defender, Layouts};
use crate::shorten::OtherwiseRule;
use crate::solver::{DefenderPlay, FollowPlay, Hand, Position, Solver, Trick};

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
    /// Lead a low card with nothing to play from the other hand, conceding
    /// the trick unless the defenders have run out.
    LeadLow(Rank),
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
            Play::LeadLow(_) => "lead low".to_string(),
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
    /// The trick ended in a way no other part's condition names; only a
    /// split's last part has it.
    Otherwise,
}

/// How a trick ended: who won it, and the plays that set it apart.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct TrickEnd {
    /// Whether declarer won the trick. For an ending merged by
    /// `collapsed_ends`, false means second hand's card took the trick, and
    /// true means the condition says only what second hand played, whoever
    /// won.
    pub declarer_won: bool,
    /// The defender whose play the condition names, and that play: normally
    /// the defender who played last, but second hand for an ending merged by
    /// `collapsed_ends`.
    pub defender: Defender,
    pub play: DefenderPlay,
    /// Second hand and its play, or None when the condition holds whatever
    /// second hand played, as when second hand made the same play in every
    /// branch the condition covers.
    pub second: Option<(Defender, DefenderPlay)>,
    /// Whether declarer played the card the trick is named by, as opposed to
    /// a different answer to second hand's play.
    pub is_as_named: bool,
}

/// Declarer's answer to a second-hand play, when the trick's name doesn't
/// imply it.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Exception {
    /// Second hand, and the play declarer answers.
    pub defender: Defender,
    pub play: DefenderPlay,
    pub answer: Answer,
}

/// What declarer plays from the third hand.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Answer {
    /// The lowest card, or one that takes the same tricks.
    Low,
    /// This card.
    Card(Rank),
}

/// A finesse: a play that wins only when a defender's card lies well.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Finesse {
    /// The defenders' group the finesse plays against: the lowest group left
    /// that could beat declarer's card.
    pub against: usize,
    /// The defender who must hold that group for the finesse to work: the
    /// one who plays before declarer's card.
    pub onside: Defender,
}

/// One trick of a line: what it does, the finesse it takes, if any, and
/// declarer's answers to second-hand plays its name doesn't imply.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Step {
    pub play: Play,
    pub finesse: Option<Finesse>,
    pub exceptions: Vec<Exception>,
    /// The cards the step's name stands for.
    pub plan: StepPlan,
}

/// The cards a step's name stands for: the hand that leads, the card it
/// leads, and the card the other hand plays when second hand plays low. It
/// records the `PlanKey` the step's branches share.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct StepPlan {
    pub leader: Hand,
    /// The card led, or None for the leader's lowest.
    pub lead: Option<Rank>,
    pub third: FollowPlay,
}

/// One continuation of a split line.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct Part {
    /// How the last trick must have gone for this part to apply.
    pub condition: Condition,
    pub line: Line,
    /// How many deals reach this part and still need it to reach the target.
    pub weight: u64,
    /// How many of those deals reach it after declarer played the card the
    /// last trick is named by.
    pub named_weight: u64,
}

/// A line of play.
#[derive(Clone, PartialEq, Eq, Debug)]
pub enum Line {
    /// Nothing left to decide: the tricks still wanted come from winners, or
    /// can't come at all.
    Done,
    /// A trick's play, then the rest of the line.
    Play(Step, Box<Line>),
    /// Different continuations, depending on how the last trick went.
    Split(Vec<Part>),
}

impl Line {
    /// The tricks along the line's likeliest path, in order: at each split,
    /// the part that the most deals reach.
    pub fn main_path(&self) -> Vec<Step> {
        let mut steps = Vec::new();
        let mut line = self;
        loop {
            match line {
                Line::Done => return steps,
                Line::Play(step, rest) => {
                    steps.push(step.clone());
                    line = rest;
                }
                // Prefer the trick as named, as when second hand plays low;
                // then the most deals overall.
                Line::Split(parts) => {
                    line = &parts
                        .iter()
                        .max_by_key(|part| (part.named_weight, part.weight))
                        .expect("a split has parts")
                        .line;
                }
            }
        }
    }

    /// How many parts the line's splits have in all, each with a condition
    /// to read.
    pub fn part_count(&self) -> usize {
        match self {
            Line::Done => 0,
            Line::Play(_, rest) => rest.part_count(),
            Line::Split(parts) => {
                parts.iter().map(|part| 1 + part.line.part_count()).sum()
            }
        }
    }
}

/// The line in words, such as "Low to the T, then low to the Q".
///
/// A line that splits within a split reads as an outline instead, one
/// bullet per condition, since run-on sentences would hide which condition
/// each part answers.
pub fn line_words(line: &Line, layouts: &Layouts) -> String {
    if split_depth(line) < 2 {
        return capitalize(&lowercase_words(line, layouts));
    }
    let mut lines = Vec::new();
    push_outline(line, layouts, None, 0, &mut lines);
    lines.join("\n")
}

/// How deeply the line's splits nest.
fn split_depth(line: &Line) -> usize {
    match line {
        Line::Done => 0,
        Line::Play(_, rest) => split_depth(rest),
        Line::Split(parts) => {
            1 + parts
                .iter()
                .map(|part| split_depth(&part.line))
                .max()
                .unwrap_or(0)
        }
    }
}

/// Add the outline of `line` to `lines`, as a bullet labeled with
/// `condition` at `depth`, or as the opening sentence when it has no
/// condition.
fn push_outline(
    line: &Line,
    layouts: &Layouts,
    condition: Option<&Condition>,
    depth: usize,
    lines: &mut Vec<String>,
) {
    let mut steps = Vec::new();
    let mut rest = line;
    while let Line::Play(step, next) = rest {
        steps.push(step.clone());
        rest = next;
    }
    let words = chain_words(&steps, layouts);
    match condition {
        None => lines.push(format!("{}.", capitalize(&words))),
        Some(condition) => {
            let indent = "  ".repeat(depth - 1);
            let label = condition_words(condition, layouts);
            if words.is_empty() {
                lines.push(format!("{indent}- {label}:"));
            } else {
                lines.push(format!("{indent}- {label}, {words}."));
            }
        }
    }
    if let Line::Split(parts) = rest {
        for part in parts {
            push_outline(
                &part.line,
                layouts,
                Some(&part.condition),
                depth + 1,
                lines,
            );
        }
    }
}

/// The line in words, starting in lowercase.
fn lowercase_words(line: &Line, layouts: &Layouts) -> String {
    match line {
        Line::Done => "cash the winners".to_string(),
        Line::Play(..) => {
            let mut steps = Vec::new();
            let mut rest = line;
            while let Line::Play(step, next) = rest {
                steps.push(step.clone());
                rest = next;
            }
            let words = chain_words(&steps, layouts);
            match rest {
                Line::Split(_) => {
                    format!("{words}. {}", lowercase_words(rest, layouts))
                }
                _ => words,
            }
        }
        Line::Split(parts) => parts
            .iter()
            .map(|part| {
                let words = lowercase_words(&part.line, layouts);
                let sentence = format!(
                    "{}, {}",
                    condition_words(&part.condition, layouts),
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

/// Consecutive plays in words, joined with "then", such as "low to the T,
/// then low to the Q".
///
/// Running a card and then each next card down the same touching sequence
/// reads as the first run alone, "run the Q" for QJT, since running a
/// sequence means running it card by card.
fn chain_words(steps: &[Step], layouts: &Layouts) -> String {
    let mut words: Vec<String> = Vec::new();
    let mut last_run: Option<Rank> = None;
    for step in steps {
        if let Play::Run(card) = step.play {
            // A run with answers of its own is spelled out, answers and all.
            let continues_run = step.exceptions.is_empty()
                && last_run.is_some_and(|higher| {
                    is_next_in_sequence(layouts, higher, card)
                });
            last_run = Some(card);
            if continues_run {
                continue;
            }
        } else {
            last_run = None;
        }
        words.push(step_words(step, layouts));
    }
    words.join(", then ")
}

/// A step in words: its play, then any answers its name doesn't imply, such
/// as "low to the Q (if West plays the K, play low)".
pub(crate) fn step_words(step: &Step, layouts: &Layouts) -> String {
    let play = step.play.words();
    if step.exceptions.is_empty() {
        return play;
    }
    let answers: Vec<String> = step
        .exceptions
        .iter()
        .map(|exception| {
            let answer = match exception.answer {
                Answer::Low => "play low".to_string(),
                Answer::Card(card) => format!("play the {}", rank_symbol(card)),
            };
            format!(
                "if {} {}, {answer}",
                defender_name(exception.defender),
                second_play_words(layouts, exception.play)
            )
        })
        .collect();
    format!("{play} ({})", answers.join("; "))
}

/// A defender's name, such as "West".
fn defender_name(defender: Defender) -> &'static str {
    match defender {
        Defender::West => "West",
        Defender::East => "East",
    }
}

/// Second hand's play in words, such as "plays the K" or "shows out".
fn second_play_words(layouts: &Layouts, play: DefenderPlay) -> String {
    match play {
        DefenderPlay::Group(group) => {
            format!("plays {}", group_words(layouts, group))
        }
        DefenderPlay::ShowOut => "shows out".to_string(),
    }
}

/// Whether `lower` sits just below `higher` in one hand's touching sequence,
/// with no card of any other hand between them.
fn is_next_in_sequence(layouts: &Layouts, higher: Rank, lower: Rank) -> bool {
    let combination = layouts.combination;
    [combination.north, combination.south]
        .into_iter()
        .any(|hand| {
            lower < higher
                && hand.contains(higher)
                && hand.contains(lower)
                && RankSet::strictly_between(higher, lower)
                    .difference(hand)
                    .is_empty()
        })
}

/// A condition in words, such as "If that wins".
pub(crate) fn condition_words(
    condition: &Condition,
    layouts: &Layouts,
) -> String {
    let ends = match condition {
        Condition::Wins => return "If that wins".to_string(),
        Condition::Loses => return "If it loses".to_string(),
        Condition::Otherwise => return "Otherwise".to_string(),
        Condition::Ended(ends) => ends,
    };
    // Whether second hand's card took the trick, beating fourth hand's.
    let is_won_by_second = |end: &TrickEnd| match (end.second, end.play) {
        (Some((_, DefenderPlay::Group(second))), fourth)
            if !end.declarer_won =>
        {
            match fourth {
                DefenderPlay::ShowOut => true,
                DefenderPlay::Group(fourth) => {
                    layouts.groups[second].top() > layouts.groups[fourth].top()
                }
            }
        }
        _ => false,
    };
    // One phrase per defender and kind of ending, such as "East plays the T
    // or a low card", after any second-hand play that sets it apart.
    let mut phrases: Vec<String> = Vec::new();
    // Who a phrase speaks of: second hand's play if named, the defender the
    // phrase is about, and whether second hand won the trick.
    type Speaker = (Option<(Defender, DefenderPlay)>, Defender, bool);
    let mut speakers: Vec<Speaker> = Vec::new();
    for end in ends {
        let speaker = (end.second, end.defender, is_won_by_second(end));
        if !speakers.contains(&speaker) {
            speakers.push(speaker);
        }
    }
    for (second, defender, by_second) in speakers {
        let start = phrases.len();
        let mine = ends.iter().filter(|end| {
            end.defender == defender
                && end.second == second
                && is_won_by_second(end) == by_second
        });
        let played: Vec<String> = mine
            .clone()
            .filter(|end| end.declarer_won || by_second)
            .filter_map(|end| match end.play {
                DefenderPlay::Group(group) => Some(group_words(layouts, group)),
                DefenderPlay::ShowOut => None,
            })
            .collect();
        if !played.is_empty() {
            phrases.push(format!(
                "{} plays {}",
                defender_name(defender),
                played.join(" or ")
            ));
        }
        if mine.clone().any(|end| end.play == DefenderPlay::ShowOut) {
            phrases.push(format!("{} shows out", defender_name(defender)));
        }
        let winners: Vec<String> = mine
            .filter(|end| !end.declarer_won && !by_second)
            .filter_map(|end| match end.play {
                DefenderPlay::Group(group) => Some(group_words(layouts, group)),
                DefenderPlay::ShowOut => None,
            })
            .collect();
        if !winners.is_empty() {
            phrases.push(format!(
                "{} wins with {}",
                defender_name(defender),
                winners.join(" or ")
            ));
        }
        if let Some((second_defender, second_play)) = second {
            let action = match second_play {
                DefenderPlay::Group(group) if by_second => {
                    format!("wins with {}", group_words(layouts, group))
                }
                _ => second_play_words(layouts, second_play),
            };
            let before = format!("{} {action}", defender_name(second_defender));
            for phrase in &mut phrases[start..] {
                *phrase = format!("{before} and {phrase}");
            }
        }
    }
    format!("If {}", phrases.join(", or "))
}

/// A defender's group in words, such as "the K" or "a low card".
fn group_words(layouts: &Layouts, group: usize) -> String {
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
pub(crate) struct Plan {
    pub(crate) leader: Hand,
    pub(crate) lead: Rank,
    pub(crate) third: FollowPlay,
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

/// The reply that the trick's name, `play`, implies when second hand plays
/// `second`, for the plan `named`: the card the trick is named by while that
/// still wins, as it does over a show-out, and otherwise the cheapest card
/// that wins the trick, or else a low card. A trick named as ducked plays low
/// throughout.
pub(crate) fn implied_reply(
    layouts: &Layouts,
    position: Position,
    named: Plan,
    play: Play,
    second: DefenderPlay,
) -> FollowPlay {
    let partner_cards = position.hand(named.leader.partner());
    let Some(lowest) = partner_cards.lowest() else {
        return FollowPlay::Discard;
    };
    if matches!(play, Play::Duck(_) | Play::LeadLow(_)) {
        return FollowPlay::Card(lowest);
    }
    let DefenderPlay::Group(group) = second else {
        return named.third;
    };
    let top = layouts.groups[group].top();
    if top < named.winner() {
        return named.third;
    }
    let cheapest_winner =
        partner_cards.intersection(RankSet::above(top)).lowest();
    FollowPlay::Card(cheapest_winner.unwrap_or(lowest))
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
    /// Whether the play gives up the trick, which changes what its name
    /// implies: low cards throughout, where any other play wins second
    /// hand's higher card as cheaply as it can.
    ducks: bool,
}

/// A plan that achieves what a branch requires.
#[derive(Clone, Debug)]
struct Candidate {
    key: PlanKey,
    /// What the plan does, as named in this branch.
    play: Play,
    /// The finesse the plan takes, if any.
    finesse: Option<Finesse>,
    plan: Plan,
    /// Declarer's answer to each play second hand might make where the line
    /// can still succeed.
    answers: Vec<Answered>,
    /// The entries the plan costs: one when it leads from the hand that
    /// didn't win the last trick.
    entries: u32,
    /// Ranks the candidate among ties, lowest first, as `Preference`
    /// describes.
    preference: Preference,
}

/// A candidate's rank among ties, lowest first: a plan whose named card is
/// really played before one second hand never lets it play, then the lower
/// set of equivalent cards, then the lower run of touching cards, then the
/// higher card within a run.
type Preference = (bool, Rank, Rank, i8);

impl Candidate {
    /// This candidate's answer to each second-hand play: the instruction
    /// `agreed` settles on, or for a play no other branch answers, its own
    /// first.
    fn settled(&self, agreed: &[Agreement]) -> Vec<Settled> {
        self.answers
            .iter()
            .map(|answered| {
                let instruction = agreed
                    .iter()
                    .find(|agreement| agreement.play == answered.play)
                    .map_or(answered.instructions[0], |agreement| {
                        agreement.instructions[0]
                    });
                Settled {
                    play: answered.play,
                    reply: answered.reply(instruction),
                    exception: instruction,
                }
            })
            .collect()
    }

    /// The answers in `settled` that the trick's name doesn't imply.
    fn exceptions(&self, settled: &[Settled]) -> Vec<Exception> {
        settled
            .iter()
            .filter_map(|each| {
                each.exception.map(|answer| Exception {
                    defender: self.plan.leader.next_defender(),
                    play: each.play,
                    answer,
                })
            })
            .collect()
    }
}

/// The instructions that keep a branch's requirement after one of second
/// hand's plays. An instruction is an answer the description states, or
/// None for the reply the trick's name implies, which each branch works out
/// for itself, so that branches whose implied replies are different cards
/// can still share a play.
#[derive(Clone, Debug)]
struct Answered {
    play: DefenderPlay,
    /// Every instruction that keeps the requirement, the most natural
    /// first: the implied reply, the cheapest card that wins the trick, then
    /// the rest from the bottom up.
    instructions: Vec<Option<Answer>>,
    /// The reply the trick's name implies.
    implied: FollowPlay,
    /// The third hand's lowest card, when it has one.
    lowest: Option<Rank>,
}

impl Answered {
    /// The card `instruction` plays in this branch.
    fn reply(&self, instruction: Option<Answer>) -> FollowPlay {
        match instruction {
            None => self.implied,
            Some(Answer::Low) => FollowPlay::Card(
                self.lowest.expect("only a hand with cards plays low"),
            ),
            Some(Answer::Card(card)) => FollowPlay::Card(card),
        }
    }
}

/// Declarer's settled answer to one of second hand's plays.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct Settled {
    play: DefenderPlay,
    reply: FollowPlay,
    /// The answer as the description states it, or None when the trick's
    /// name implies it.
    exception: Option<Answer>,
}

/// The instructions that every branch sharing a play allows after one of
/// second hand's plays, the most natural first.
#[derive(Clone, Debug)]
struct Agreement {
    play: DefenderPlay,
    instructions: Vec<Option<Answer>>,
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

/// The cost added to a description whose conditions can't tell two of its
/// continuations apart, so that any clear description wins over it.
const AMBIGUOUS: u32 = 1_000_000;

/// How many of the candidate plays common to every branch the description
/// tries at each trick, in order of preference. Each one tried describes the
/// rest of the line afresh, so the limit keeps long lines quick.
const PLAYS_TRIED: usize = 4;

/// Describes strategies using a solver's frontiers.
pub struct Describer<'s, 'a> {
    solver: &'s mut Solver<'a>,
}

impl<'s, 'a> Describer<'s, 'a> {
    /// A describer drawing on `solver`'s frontiers, which it asks the solver
    /// to remember within each trick.
    pub fn new(solver: &'s mut Solver<'a>) -> Describer<'s, 'a> {
        solver.remember_tricks();
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
        let hard_slices: Vec<&[Candidate]> =
            hard_options.iter().map(Vec::as_slice).collect();
        let soft_slices: Vec<&[Candidate]> =
            soft_options.iter().map(Vec::as_slice).collect();
        let common: Vec<PlanKey> = common_keys(&hard_options)
            .into_iter()
            .filter(|&key| {
                select(&hard_slices, key, &[]).0.iter().all(Option::is_some)
            })
            .collect();

        let mut best: Option<(Cost, Line)> = None;
        for key in common.into_iter().take(PLAYS_TRIED) {
            let (hard_chosen, agreed) = select(&hard_slices, key, &[]);
            // A branch only making overtricks goes along when the replies
            // the others settle on suit it too.
            let soft_chosen = soft_slices.iter().map(|each| {
                let mut matching: Vec<&Candidate> = each
                    .iter()
                    .filter(|candidate| candidate.key == key)
                    .collect();
                matching.sort_by_key(|candidate| candidate.entries);
                matching
                    .into_iter()
                    .find(|candidate| fits(&candidate.answers, &agreed))
            });
            let mut entries = 0;
            let mut next = Vec::new();
            let mut steps = Vec::new();
            let chosen = hard
                .iter()
                .zip(hard_chosen)
                .chain(soft.iter().zip(soft_chosen));
            for (branch, candidate) in chosen {
                let Some(candidate) = candidate else {
                    continue;
                };
                let settled = candidate.settled(&agreed);
                entries += candidate.entries;
                steps.push(Step {
                    play: candidate.play,
                    finesse: candidate.finesse,
                    exceptions: candidate.exceptions(&settled),
                    plan: StepPlan {
                        leader: key.leader,
                        lead: match key.lead {
                            LeadKey::Low => None,
                            LeadKey::Card(card) => Some(card),
                        },
                        third: key.third,
                    },
                });
                next.extend(self.after(branch, candidate, &settled));
            }
            // A play that only cashes a winner in one branch may be a finesse
            // in another, and the finesse is the one worth naming.
            let mut step = steps
                .iter()
                .min_by_key(|step| naming_rank(step.play))
                .cloned()
                .expect("every key has a candidate in the first branch");
            // Each branch answers its own second-hand plays, and the step
            // states every answer its name doesn't imply, once.
            step.exceptions = Vec::new();
            for exception in steps.iter().flat_map(|step| &step.exceptions) {
                let is_new = step.exceptions.iter().all(|stated| {
                    (stated.defender, stated.play)
                        != (exception.defender, exception.play)
                });
                if is_new {
                    step.exceptions.push(*exception);
                }
            }
            let (rest_cost, rest) = self.describe_branches(next);
            let cost = (
                rest_cost.0.saturating_add(entries),
                rest_cost.1.saturating_add(1),
            );
            if best.as_ref().is_none_or(|(best_cost, _)| cost < *best_cost) {
                best = Some((cost, Line::Play(step, Box::new(rest))));
            }
        }
        // Splitting on how the last trick ended can only help when it
        // separates the branches.
        let endings = dedup(hard.iter().map(|branch| branch.ended));
        let can_split_now = endings.len() > 1 && !endings.contains(&None);
        match best {
            Some(best) if best.0.0 < AMBIGUOUS || !can_split_now => best,
            Some(best) => {
                let split =
                    self.split(hard, &hard_options, soft, Grouping::ByEnding);
                if split.0 < best.0 { split } else { best }
            }
            None => self.split(hard, &hard_options, soft, Grouping::ByPlay),
        }
    }

    /// Separate lines for the branches, grouped as `grouping` says: by a
    /// play they share, when no single play suits them all, or by how their
    /// last trick ended, when merging them would leave a later split
    /// ambiguous.
    fn split(
        &mut self,
        hard: Vec<Branch>,
        options: &[Vec<Candidate>],
        soft: Vec<Branch>,
        grouping: Grouping,
    ) -> (Cost, Line) {
        let mut remaining: Vec<usize> = (0..hard.len()).collect();
        let mut groups: Vec<Vec<usize>> = Vec::new();
        if grouping == Grouping::ByEnding {
            for ending in dedup(hard.iter().map(|branch| branch.ended)) {
                groups.push(
                    remaining
                        .iter()
                        .copied()
                        .filter(|&index| hard[index].ended == ending)
                        .collect(),
                );
            }
            remaining.clear();
        }
        // Each group takes the play that suits the most branches left, with
        // answers that agree.
        while !remaining.is_empty() {
            let remaining_options: Vec<&[Candidate]> = remaining
                .iter()
                .map(|&index| options[index].as_slice())
                .collect();
            let mut best_key: Option<(usize, Preference, PlanKey)> = None;
            for &index in &remaining {
                for candidate in &options[index] {
                    let count = select(&remaining_options, candidate.key, &[])
                        .0
                        .iter()
                        .filter(|chosen| chosen.is_some())
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
            let (chosen, _) = select(&remaining_options, key, &[]);
            let mut group = Vec::new();
            let mut rest = Vec::new();
            for (&index, candidate) in remaining.iter().zip(chosen) {
                if candidate.is_some() {
                    group.push(index);
                } else {
                    rest.push(index);
                }
            }
            groups.push(group);
            remaining = rest;
        }

        // Describe each group, merging groups whose lines read the same.
        let mut cost: Cost = (0, 0);
        let mut described: Vec<(Vec<usize>, Line, String)> = Vec::new();
        for group in groups {
            let ends: Vec<TrickEnd> = dedup(group.iter().map(|&index| {
                hard[index].ended.expect("a split follows a trick")
            }));
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
            cost = (
                cost.0.saturating_add(part_cost.0),
                cost.1.saturating_add(part_cost.1),
            );
            let words = lowercase_words(&line, self.solver.layouts);
            match described.iter_mut().find(|(_, _, other)| *other == words) {
                Some((merged, _, _)) => merged.extend(group),
                None => described.push((group, line, words)),
            }
        }

        let all_won: Vec<usize> = (0..hard.len())
            .filter(|&index| {
                hard[index].ended.is_some_and(|end| end.declarer_won)
            })
            .collect();
        // "If it loses" and "If that wins" speak of the card the trick is
        // named by, so they suit only a trick played as named.
        let is_all_as_named = hard
            .iter()
            .all(|branch| branch.ended.is_some_and(|end| end.is_as_named));
        // When second hand played the same card every way the trick went,
        // conditions leave it out; otherwise each says what second hand
        // played, since a condition naming only fourth hand's card would also
        // seem to hold after second hand's other cards.
        let is_one_second = dedup(
            hard.iter()
                .map(|branch| branch.ended.and_then(|end| end.second)),
        )
        .len()
            == 1;
        let mut parts = Vec::new();
        // An ending that two groups share would leave its condition naming
        // two different continuations.
        let mut seen_ends: Vec<TrickEnd> = Vec::new();
        let mut is_ambiguous = false;
        // "If that wins" and "If it loses" cover every trick won or lost, so
        // they stand only as the split's sole two parts.
        let is_two_way = described.len() == 2;
        for (mut group, line, _) in described {
            group.sort_unstable();
            let ends = if is_one_second {
                dedup(group.iter().map(|&index| TrickEnd {
                    second: None,
                    ..hard[index].ended.expect("a split follows a trick")
                }))
            } else {
                collapsed_ends(self.solver.layouts, &hard, &group)
            };
            if ends.iter().any(|end| seen_ends.contains(end)) {
                is_ambiguous = true;
            }
            seen_ends.extend(ends.iter().copied());
            let is_by_outcome = is_all_as_named
                && is_two_way
                && groups_by_outcome(&group, &all_won, hard.len());
            let condition = if is_by_outcome {
                if group == all_won {
                    Condition::Wins
                } else {
                    Condition::Loses
                }
            } else {
                Condition::Ended(ends)
            };
            let weight_of = |index: &&usize| {
                self.solver.layouts.weight(hard[**index].required[0])
            };
            let weight = group.iter().map(|index| weight_of(&index)).sum();
            let named_weight = group
                .iter()
                .filter(|&&index| {
                    hard[index].ended.is_some_and(|end| end.is_as_named)
                })
                .map(|index| weight_of(&index))
                .sum();
            // A group that splits again before any play splits on this same
            // trick, but nests: its conditions only tell apart the group's
            // own branches, and beside the others they could overlap theirs.
            parts.push(Part {
                condition,
                line,
                weight,
                named_weight,
            });
        }
        // Read literally, as a reader would, each way the trick went must
        // meet the condition of only one part, or of several parts whose
        // lines read the same.
        let part_words: Vec<String> = parts
            .iter()
            .map(|part| lowercase_words(&part.line, self.solver.layouts))
            .collect();
        for branch in &hard {
            let Some(ending) = branch.ended.and_then(check::Ending::of) else {
                continue;
            };
            let met = dedup(
                parts
                    .iter()
                    .zip(&part_words)
                    .filter(|(part, _)| ending.meets(&part.condition))
                    .map(|(_, words)| words),
            );
            if met.len() != 1 {
                is_ambiguous = true;
            }
        }
        if is_ambiguous {
            cost.0 = cost.0.saturating_add(AMBIGUOUS);
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
        let mut candidates = Vec::new();
        for (leader, lead) in self.solver.leads(position) {
            let trick = Trick::led(position, leader, lead);
            // Second hand's plays, leaving out any made only where the line
            // has already failed: declarer's answer to such a play changes
            // nothing, so the description never follows it.
            let options: Vec<(DefenderPlay, LayoutSet)> = self
                .solver
                .defender_options(trick)
                .into_iter()
                .filter(|&(_, layouts)| {
                    branch
                        .required
                        .iter()
                        .any(|set| !set.intersection(layouts).is_empty())
                })
                .collect();
            // Whether declarer, answering freely, can still meet the
            // requirement after each of second hand's plays.
            let free: Vec<bool> = options
                .iter()
                .map(|&(play, layouts)| {
                    self.solver
                        .third_hand_turn(trick.with_defender_play(play))
                        .achieves(&restricted(&branch.required, layouts))
                })
                .collect();

            // Plans whose third card answers second hand's low play: its
            // lowest below the card declarer means to win with. Each of
            // second hand's plays can be checked on its own, since the
            // defenders choose between them layout by layout.
            for (index, &(low, low_layouts)) in options.iter().enumerate() {
                let others_work = free
                    .iter()
                    .enumerate()
                    .all(|(other, &works)| other == index || works);
                if !others_work {
                    continue;
                }
                let low_trick = trick.with_defender_play(low);
                let required = restricted(&branch.required, low_layouts);
                for third in self.solver.third_hand_options(low_trick) {
                    let plan = Plan {
                        leader,
                        lead,
                        third,
                    };
                    if self.low_play(&options, plan) != Some(low) {
                        continue;
                    }
                    let child =
                        self.solver.defender_turn(low_trick.with_third(third));
                    if child.achieves(&required) {
                        self.add_candidates(
                            &mut candidates,
                            branch,
                            plan,
                            (low, third),
                            low,
                            false,
                            &options,
                        );
                    }
                }
            }

            // Plans that second hand can never play below: declarer answers
            // whatever comes freely, so only the lead is fixed.
            if !free.iter().all(|&works| works) {
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
                        true,
                        &options,
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
        let required = restricted(&branch.required, layouts);
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
    #[allow(clippy::too_many_arguments)]
    fn add_candidates(
        &mut self,
        candidates: &mut Vec<Candidate>,
        branch: &Branch,
        plan: Plan,
        main_line: (DefenderPlay, FollowPlay),
        second: DefenderPlay,
        is_free: bool,
        options: &[(DefenderPlay, LayoutSet)],
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
                let main_line = if main_line.1 == plan.third {
                    (main_line.0, third)
                } else {
                    main_line
                };
                // Every branch names the trick by the same plan, the card led
                // and the card meant for second hand's low card, even where
                // second hand has none at stake: every other answer then
                // follows from that one name, or is stated beside it.
                let winner = named.winner();
                let winner_cards = if named.winning_hand() == plan.leader {
                    leader_cards
                } else {
                    partner_cards
                };
                let play = self.classify(position, named, leads_low);
                // Every branch names the trick by the same plan, the card led
                // and the card meant for second hand's low card, even where
                // second hand has no low card to play: every other answer
                // then follows from that one name, or is stated beside it.
                let key = PlanKey {
                    leader: plan.leader,
                    lead: if leads_low {
                        LeadKey::Low
                    } else {
                        LeadKey::Card(lead)
                    },
                    third,
                    ducks: matches!(play, Play::Duck(_) | Play::LeadLow(_)),
                };
                // A free plan names a card for second hand's low card, which
                // second hand never plays; one naming the card it really
                // plays reads truer, as "Cash the A" against "Lead the 5 and
                // play the 4" when East can only drop a singleton K.
                let is_hypothetical = is_free && main_line.1 != third;
                let preference =
                    if matches!(play, Play::Duck(_) | Play::LeadLow(_)) {
                        // Giving up a trick is the last resort among ties.
                        (is_hypothetical, Rank::MAX, Rank::MAX, 0)
                    } else {
                        (
                            is_hypothetical,
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
                let answers = self
                    .answers(branch, named, play, main_line, is_free, options)
                    .expect("a valid plan answers every second-hand play");
                candidates.push(Candidate {
                    key,
                    play,
                    finesse: self.finesse(position, named, play),
                    plan: named,
                    answers,
                    entries,
                    preference,
                });
            }
        }
    }

    /// The instructions that keep the branch's requirement after each of
    /// second hand's `options`, once `named` leads: for the low play `named`
    /// answers, the play itself; for any other, the instructions that work,
    /// as `Answered` describes them. A free plan, one second hand can never
    /// play below, has no such low play. None when some play has no
    /// instruction that works.
    fn answers(
        &mut self,
        branch: &Branch,
        named: Plan,
        play: Play,
        main_line: (DefenderPlay, FollowPlay),
        is_free: bool,
        options: &[(DefenderPlay, LayoutSet)],
    ) -> Option<Vec<Answered>> {
        let position = branch.position;
        let partner_cards = position.hand(named.leader.partner());
        let led = Trick::led(position, named.leader, named.lead);
        let mut answers = Vec::new();
        for &(second, layouts) in options {
            let contested = match second {
                DefenderPlay::Group(group) => {
                    self.solver.layouts.groups[group].ranks
                }
                DefenderPlay::ShowOut => RankSet::EMPTY,
            };
            let lowest = partner_cards.lowest();
            let low_cards = lowest.map_or(RankSet::EMPTY, |lowest| {
                self.solver.equivalent_cards(
                    position,
                    partner_cards,
                    lowest,
                    contested,
                )
            });
            // A reply stated outright: playing low when it takes the same
            // tricks as the lowest card.
            let stated = |reply: FollowPlay| match reply {
                FollowPlay::Card(card) if low_cards.contains(card) => {
                    Some(Answer::Low)
                }
                FollowPlay::Card(card) => Some(Answer::Card(card)),
                FollowPlay::Discard => None,
            };
            if second == main_line.0 && !is_free {
                answers.push(Answered {
                    play: second,
                    instructions: dedup(
                        [None, stated(main_line.1)].into_iter(),
                    ),
                    implied: main_line.1,
                    lowest,
                });
                continue;
            }
            let implied = implied_reply(
                self.solver.layouts,
                position,
                named,
                play,
                second,
            );
            // After the implied reply, tried first below: the cheapest card
            // that wins the trick, then every card from the bottom up.
            let mut cards: Vec<Rank> = Vec::new();
            if let DefenderPlay::Group(group) = second {
                let top = self.solver.layouts.groups[group].top();
                cards.extend(
                    partner_cards.intersection(RankSet::above(top)).lowest(),
                );
            }
            let mut ascending: Vec<Rank> = partner_cards.descending().collect();
            ascending.reverse();
            cards.extend(ascending);
            let tried = std::iter::once(implied)
                .chain(cards.into_iter().map(FollowPlay::Card));
            let required = restricted(&branch.required, layouts);
            let played = led.with_defender_play(second);
            // Cards that take the same tricks as the implied reply count as
            // implied too.
            let implied_cards = match implied {
                FollowPlay::Card(card) => self.solver.equivalent_cards(
                    position,
                    partner_cards,
                    card,
                    contested,
                ),
                FollowPlay::Discard => RankSet::EMPTY,
            };
            let mut instructions = Vec::new();
            for reply in dedup(tried) {
                let keeps = self
                    .solver
                    .defender_turn(played.with_third(reply))
                    .achieves(&required);
                if !keeps {
                    continue;
                }
                let is_implied = match reply {
                    FollowPlay::Card(card) => implied_cards.contains(card),
                    FollowPlay::Discard => true,
                };
                if is_implied {
                    instructions.push(None);
                }
                // The implied reply is also offered stated outright, so that
                // it can agree with a branch that states the same card.
                instructions.extend(stated(reply).map(Some));
            }
            if instructions.is_empty() {
                return None;
            }
            answers.push(Answered {
                play: second,
                instructions: dedup(instructions.into_iter()),
                implied,
                lowest,
            });
        }
        Some(answers)
    }

    /// The finesse `plan` takes, if it takes one: a lead toward a card, or a
    /// lead of a card, that a defender's card still outranks. `play` is what
    /// the plan does, as `classify` names it.
    fn finesse(
        &self,
        position: Position,
        plan: Plan,
        play: Play,
    ) -> Option<Finesse> {
        let is_finesse = match play {
            Play::Toward { .. } | Play::Run(_) | Play::Lead(_) => true,
            Play::Cash(_)
            | Play::Duck(_)
            | Play::LeadLow(_)
            | Play::Other { .. } => false,
        };
        if !is_finesse {
            return None;
        }
        let groups = &self.solver.layouts.groups;
        let against = (0..groups.len()).rev().find(|&group| {
            let played =
                position.played[0].get(group) + position.played[1].get(group);
            played < groups[group].size() && groups[group].top() > plan.winner()
        })?;
        Some(Finesse {
            against,
            onside: plan.leader.next_defender(),
        })
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
            let leader_cards = position.hand(plan.leader);
            let is_lowest = leader_cards.lowest().is_some_and(|lowest| {
                self.solver
                    .equivalent_cards(
                        position,
                        leader_cards,
                        lowest,
                        RankSet::EMPTY,
                    )
                    .contains(plan.lead)
            });
            return if is_top(plan.lead) {
                Play::Cash(plan.lead)
            } else if is_lowest
                && missing.lowest().is_some_and(|lowest| plan.lead < lowest)
            {
                Play::LeadLow(plan.lead)
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
    fn after(
        &mut self,
        branch: &Branch,
        candidate: &Candidate,
        settled: &[Settled],
    ) -> Vec<Branch> {
        let plan = candidate.plan;
        let led = Trick::led(branch.position, plan.leader, plan.lead);
        let named_reply = candidate.plan.third;
        let mut branches = Vec::new();
        for answer in settled {
            let second = Some((plan.leader.next_defender(), answer.play));
            // Even an implied answer, such as playing low under a card
            // declarer can't beat, leaves the named card unplayed.
            let is_as_named = answer.reply == named_reply;
            branches.extend(self.after_second(
                branch,
                led,
                *answer,
                second,
                is_as_named,
            ));
        }
        branches
    }

    /// The branches after second hand plays `answer.play` and the third hand
    /// answers, one for each play fourth hand might make. `second` names
    /// second hand and its play when those set the branches apart, and
    /// `is_as_named` says whether declarer played the card the trick is
    /// named by.
    fn after_second(
        &mut self,
        branch: &Branch,
        led: Trick,
        answer: Settled,
        second: Option<(Defender, DefenderPlay)>,
        is_as_named: bool,
    ) -> Vec<Branch> {
        let third = answer.reply;
        let trick = led.with_defender_play(answer.play).with_third(third);
        let layouts = self.solver.layouts;
        let mut branches = Vec::new();
        for (play, _) in self.solver.defender_options(trick) {
            let done = trick.with_defender_play(play);
            let position = done.next_position(layouts);
            let required =
                restricted(&branch.required, self.solver.live(position));
            let declarer_won = done.declarer_wins(layouts);
            let winning_hand = match third {
                FollowPlay::Card(card) if card > led.lead => {
                    led.leader.partner()
                }
                _ => led.leader,
            };
            branches.push(Branch {
                position,
                required,
                hand_in: declarer_won.then_some(winning_hand),
                ended: Some(TrickEnd {
                    declarer_won,
                    defender: led.leader.last_defender(),
                    play,
                    second,
                    is_as_named,
                }),
            });
        }
        branches
    }

    /// Checks that `line`, played the way a reader would play it (see
    /// `crate::check`), reaches the solver's lowest target in every layout of
    /// `required[0]`. The error says where the line falls short.
    pub fn check(
        &mut self,
        line: &Line,
        required: &[LayoutSet],
    ) -> Result<(), String> {
        crate::check::check(self.solver, line, required)
    }

    /// `line`, shortened by every rewrite that keeps it passing `check`,
    /// choosing each split's "Otherwise" by `rule`, as `crate::shorten`
    /// describes.
    pub(crate) fn shorten(
        &mut self,
        line: Line,
        required: &[LayoutSet],
        rule: OtherwiseRule,
    ) -> Line {
        crate::shorten::shorten(self.solver, line, required, rule)
    }
}

/// How well a play's name explains a trick, lower being better: a branch where
/// the play is a finesse names it better than one where it ducks, and either
/// better than one where it merely cashes a winner.
fn naming_rank(play: Play) -> u8 {
    match play {
        Play::Toward { .. }
        | Play::Run(_)
        | Play::Lead(_)
        | Play::Other { .. } => 0,
        Play::Duck(_) | Play::LeadLow(_) => 1,
        Play::Cash(_) => 2,
    }
}

/// How a split groups its branches.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Grouping {
    /// Together whenever one play suits them.
    ByPlay,
    /// By how the last trick ended, one group per ending.
    ByEnding,
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

/// `required` cut down to the layouts in `layouts`.
pub(crate) fn restricted(
    required: &[LayoutSet],
    layouts: LayoutSet,
) -> Vec<LayoutSet> {
    required
        .iter()
        .map(|set| set.intersection(layouts))
        .collect()
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

/// For each branch's candidates in `options`, the one with `key` that costs
/// the fewest entries among those that allow, for every second-hand play,
/// an instruction the branches chosen so far allow too, starting from
/// `agreed`; None for a branch with no such candidate. Returns the choices,
/// and the instructions they all allow.
fn select<'c>(
    options: &[&'c [Candidate]],
    key: PlanKey,
    agreed: &[Agreement],
) -> (Vec<Option<&'c Candidate>>, Vec<Agreement>) {
    let mut agreed = agreed.to_vec();
    let mut chosen = Vec::new();
    for each in options {
        let mut matching: Vec<&Candidate> = each
            .iter()
            .filter(|candidate| candidate.key == key)
            .collect();
        matching.sort_by_key(|candidate| candidate.entries);
        let choice = matching
            .into_iter()
            .find(|candidate| agrees(&candidate.answers, &agreed));
        if let Some(candidate) = choice {
            agreed = narrowed(&agreed, &candidate.answers);
        }
        chosen.push(choice);
    }
    (chosen, agreed)
}

/// Whether `answers` allow, for every second-hand play `agreed` covers, an
/// instruction `agreed` allows too, so that one description can fit them
/// both.
fn agrees(answers: &[Answered], agreed: &[Agreement]) -> bool {
    answers.iter().all(|answered| {
        agreed
            .iter()
            .filter(|agreement| agreement.play == answered.play)
            .all(|agreement| {
                agreement.instructions.iter().any(|instruction| {
                    answered.instructions.contains(instruction)
                })
            })
    })
}

/// Whether `answers` allow the instruction `agreed` settles on, its first,
/// for every second-hand play `agreed` covers.
fn fits(answers: &[Answered], agreed: &[Agreement]) -> bool {
    answers.iter().all(|answered| {
        agreed
            .iter()
            .filter(|agreement| agreement.play == answered.play)
            .all(|agreement| {
                answered.instructions.contains(&agreement.instructions[0])
            })
    })
}

/// `agreed`, keeping only the instructions `answers` allow too, with the
/// plays only `answers` covers added.
fn narrowed(agreed: &[Agreement], answers: &[Answered]) -> Vec<Agreement> {
    let mut narrowed: Vec<Agreement> = agreed
        .iter()
        .map(|agreement| {
            let instructions = match answers
                .iter()
                .find(|answered| answered.play == agreement.play)
            {
                Some(answered) => agreement
                    .instructions
                    .iter()
                    .copied()
                    .filter(|instruction| {
                        answered.instructions.contains(instruction)
                    })
                    .collect(),
                None => agreement.instructions.clone(),
            };
            Agreement {
                play: agreement.play,
                instructions,
            }
        })
        .collect();
    for answered in answers {
        if !agreed
            .iter()
            .any(|agreement| agreement.play == answered.play)
        {
            narrowed.push(Agreement {
                play: answered.play,
                instructions: answered.instructions.clone(),
            });
        }
    }
    narrowed
}

/// Whether `group` is exactly the branches that won, or exactly those that
/// lost, of `count` branches of which those in `won` won, with some of each.
fn groups_by_outcome(group: &[usize], won: &[usize], count: usize) -> bool {
    let has_both = !won.is_empty() && won.len() < count;
    let lost: Vec<usize> =
        (0..count).filter(|index| !won.contains(index)).collect();
    has_both && (group == won || group == lost)
}

/// The endings of the branches in `group`, with the endings after a
/// second-hand play merged into that play when the group holds every one of
/// them: the second-hand play alone then sets the group apart.
fn collapsed_ends(
    layouts: &Layouts,
    hard: &[Branch],
    group: &[usize],
) -> Vec<TrickEnd> {
    let end_of =
        |index: usize| hard[index].ended.expect("a split follows a trick");
    let mut ends = dedup(group.iter().map(|&index| end_of(index)));
    for second in dedup(ends.iter().filter_map(|end| end.second)) {
        let after = |end: &TrickEnd| end.second == Some(second);
        let holds_all = (0..hard.len())
            .filter(|&index| after(&end_of(index)))
            .all(|index| group.contains(&index));
        if !holds_all {
            continue;
        }
        let merged: Vec<TrickEnd> =
            ends.iter().copied().filter(|end| after(end)).collect();
        ends.retain(|end| !after(end));
        let (defender, play) = second;
        // The merged ending says second hand won only when its own card took
        // every one of the tricks, rather than fourth hand's.
        let second_won = merged.iter().all(|end| {
            let fourth_beaten = match (play, end.play) {
                (DefenderPlay::Group(_), DefenderPlay::ShowOut) => true,
                (DefenderPlay::Group(second), DefenderPlay::Group(fourth)) => {
                    layouts.groups[second].top() > layouts.groups[fourth].top()
                }
                (DefenderPlay::ShowOut, _) => false,
            };
            !end.declarer_won && fourth_beaten
        });
        ends.push(TrickEnd {
            declarer_won: !second_won,
            defender,
            play,
            second: None,
            is_as_named: merged.iter().all(|end| end.is_as_named),
        });
    }
    ends
}

/// `items` with repeats removed, keeping the first of each.
pub(crate) fn dedup<T: PartialEq>(items: impl Iterator<Item = T>) -> Vec<T> {
    let mut unique = Vec::new();
    for item in items {
        if !unique.contains(&item) {
            unique.push(item);
        }
    }
    unique
}
