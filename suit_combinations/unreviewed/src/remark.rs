// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The intuition behind a best line, such as "Finesse hoping the K or J is
//! onside".
//!
//! The approach is set out in `suit_combinations/spec.md` #remarks. In
//! short: the line's finesses name its technique and the defender who must
//! hold the missing honors, and the simplest condition on the layout that
//! matches where the line wins says what it hopes for.

use crate::analysis::{BestResult, percent_of_deals};
use crate::cards::rank_symbol;
use crate::describe::Finesse;
use crate::layout_set::LayoutSet;
use crate::layouts::{DEAL_COUNT, Defender, Layouts};

/// Which defender a fact about a holding concerns.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Holder {
    /// Either defender.
    Either,
    /// The defender the line's finesses need to hold the missing honors.
    Onside,
    /// The other defender.
    Offside,
}

/// A simple fact about a layout, from which conditions are built.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Fact {
    /// The onside defender holds the group's card, or at least one of its
    /// cards; with `all`, every one of them.
    Onside { group: usize, all: bool },
    /// The same, for the offside defender.
    Offside { group: usize, all: bool },
    /// The defenders' cards split as evenly as they can.
    EvenSplit,
    /// The group's single card lies with `holder` in a holding of at most
    /// `length` cards, so declarer's top cards drop it within `length`
    /// rounds.
    Short {
        group: usize,
        length: u8,
        holder: Holder,
    },
    /// This defender holds every missing card.
    HoldsAll(Defender),
}

/// A condition on the layout: a fact, by its index among the facts tried,
/// or two conditions joined.
#[derive(Clone, PartialEq, Eq, Debug)]
enum LayoutCondition {
    Fact(usize),
    And(Box<LayoutCondition>, Box<LayoutCondition>),
    Or(Box<LayoutCondition>, Box<LayoutCondition>),
}

impl LayoutCondition {
    /// How many facts the condition uses.
    fn size(&self) -> usize {
        match self {
            LayoutCondition::Fact(_) => 1,
            LayoutCondition::And(left, right)
            | LayoutCondition::Or(left, right) => left.size() + right.size(),
        }
    }
}

/// The facts a remark may use, each with the layouts where it holds.
struct Facts {
    facts: Vec<Fact>,
    holds_in: Vec<LayoutSet>,
}

impl Facts {
    /// The layouts where `condition` holds.
    fn layouts_of(&self, condition: &LayoutCondition) -> LayoutSet {
        match condition {
            LayoutCondition::Fact(index) => self.holds_in[*index],
            LayoutCondition::And(left, right) => {
                self.layouts_of(left).intersection(self.layouts_of(right))
            }
            LayoutCondition::Or(left, right) => {
                self.layouts_of(left).union(self.layouts_of(right))
            }
        }
    }
}

/// How far a condition may miss the line's real successes, as a share of all
/// deals, and still describe them; what it misses gets a mention of its own,
/// such as a singleton dropping.
const MAX_CONDITION_ERROR: f64 = 0.10;

/// How much more a simpler condition may miss, as a share of all deals, and
/// still be preferred over a more exact one.
const SIMPLICITY_TOLERANCE: f64 = 0.05;

/// The largest share of deals an extra chance may add and still be called
/// small.
const SMALL_CHANCE: f64 = 0.05;

/// The intuition behind the best lines in `best`.
pub fn remark(layouts: &Layouts, best: &[BestResult]) -> String {
    let wins = best[0].layouts_by_target[0];
    if wins == layouts.all {
        return "This line succeeds however the cards lie".to_string();
    }
    if wins.is_empty() {
        return "Best defense always holds declarer below the target"
            .to_string();
    }

    let finesses: Vec<Finesse> = best[0]
        .line
        .usual_path()
        .iter()
        .filter_map(|step| step.finesse)
        .collect();
    let onside = finesses.first().map(|finesse| finesse.onside);
    let facts = facts_worth_trying(layouts, onside);
    let success = simplest_condition(layouts, &facts, wins);
    let condition = success.as_ref().map(|(condition, _)| condition.clone());
    // Extra chances are extra to a condition; with none, there's nothing for
    // them to add to.
    let extras_words = match &condition {
        Some(condition) => {
            extras_words(layouts, wins.difference(facts.layouts_of(condition)))
        }
        None => String::new(),
    };

    let is_two_way = best.iter().any(|result| {
        let other = result
            .line
            .usual_path()
            .iter()
            .find_map(|step| step.finesse)
            .map(|finesse| finesse.onside);
        other.is_some() && other != onside
    });
    if is_two_way {
        return format!("A two-way finesse{extras_words}");
    }

    let technique = if finesses.is_empty() {
        "Play for the drop"
    } else if finesses.iter().enumerate().any(|(index, finesse)| {
        // Finessing twice against a group of two cards, such as the K and Q
        // against AJT, plays against each card once; only a single card
        // makes the finesse a repeated one.
        layouts.groups[finesse.against].size() == 1
            && finesses[..index]
                .iter()
                .any(|earlier| earlier.against == finesse.against)
    }) {
        "Repeated finesse"
    } else {
        "Finesse"
    };
    match condition {
        // A line with no finesse that needs only an even split is playing
        // for that split, not for a card to drop.
        Some(LayoutCondition::Fact(index))
            if finesses.is_empty() && facts.facts[index] == Fact::EvenSplit =>
        {
            let missing = layouts.missing_count();
            format!(
                "Play for a {}-{} split{extras_words}",
                missing.div_ceil(2),
                missing / 2
            )
        }
        _ if let Some(failure) =
            failure_words(layouts, &facts, wins, success.as_ref()) =>
        {
            format!("{technique}; it fails only when {failure}")
        }
        Some(condition) => format!(
            "{technique} hoping {}{extras_words}",
            layout_condition_words(layouts, &facts.facts, &condition)
        ),
        None => technique.to_string(),
    }
}

/// When the line fails, in words, if that says more than when it succeeds.
/// It applies only to a line that succeeds more often than not. The failure
/// condition must hold in every layout where the line fails and in few
/// others, and be exact where the success condition `success` is not, or be
/// simpler.
fn failure_words(
    layouts: &Layouts,
    facts: &Facts,
    wins: LayoutSet,
    success: Option<&(LayoutCondition, u64)>,
) -> Option<String> {
    if 2 * layouts.weight(wins) < DEAL_COUNT {
        return None;
    }
    let losses = layouts.all.difference(wins);
    let (failure, error) = simplest_condition(layouts, facts, losses)?;
    // "Fails only when" must cover every loss.
    if !facts.layouts_of(&failure).is_superset(losses) {
        return None;
    }
    let is_better = match success {
        None => true,
        Some((success, success_error)) => {
            (*success_error > 0
                && error == 0
                && failure.size() <= success.size())
                || failure.size() < success.size()
        }
    };
    is_better.then(|| layout_condition_words(layouts, &facts.facts, &failure))
}

/// The facts worth trying for a line whose finesses need the `onside`
/// defender, if any, to hold the cards they play against.
fn facts_worth_trying(layouts: &Layouts, onside: Option<Defender>) -> Facts {
    let mut facts = Vec::new();
    // The lowest group holds the small cards, never worth naming.
    let named_group_count = layouts.groups.len().saturating_sub(1);
    if onside.is_some() {
        for group in 0..named_group_count {
            for all in [false, true] {
                if !all || layouts.groups[group].size() > 1 {
                    facts.push(Fact::Onside { group, all });
                    facts.push(Fact::Offside { group, all });
                }
            }
        }
    }
    facts.push(Fact::EvenSplit);
    let holders: &[Holder] = if onside.is_some() {
        &[Holder::Onside, Holder::Offside]
    } else {
        &[Holder::Either]
    };
    for group in 0..named_group_count {
        if layouts.groups[group].size() == 1 {
            for length in 1..=2 {
                for &holder in holders {
                    facts.push(Fact::Short {
                        group,
                        length,
                        holder,
                    });
                }
            }
        }
    }
    facts.push(Fact::HoldsAll(Defender::West));
    facts.push(Fact::HoldsAll(Defender::East));
    let sets = facts
        .iter()
        .map(|&fact| fact_layouts(layouts, onside, fact))
        .collect();
    Facts {
        facts,
        holds_in: sets,
    }
}

/// The simplest condition, built from up to three of `facts`, that matches
/// `to_match` to within `MAX_CONDITION_ERROR` and more closely than saying
/// nothing would. A simpler condition wins over a closer one when it misses
/// by at most `SIMPLICITY_TOLERANCE` more. Returns the condition with its
/// error, in deals, or None when nothing comes that close.
fn simplest_condition(
    layouts: &Layouts,
    facts: &Facts,
    to_match: LayoutSet,
) -> Option<(LayoutCondition, u64)> {
    // A condition holding in every layout, or in none, says nothing.
    let error = |condition: &LayoutCondition| {
        let matched = facts.layouts_of(condition);
        if matched == layouts.all || matched.is_empty() {
            return u64::MAX;
        }
        layouts.weight(to_match.difference(matched))
            + layouts.weight(matched.difference(to_match))
    };
    let single_facts: Vec<LayoutCondition> =
        (0..facts.facts.len()).map(LayoutCondition::Fact).collect();
    let mut scored: Vec<(u64, LayoutCondition)> = single_facts
        .iter()
        .map(|condition| (error(condition), condition.clone()))
        .collect();
    let is_exact = |scored: &[(u64, LayoutCondition)]| {
        scored.iter().any(|(error, _)| *error == 0)
    };
    // Larger conditions can only help when nothing smaller fits exactly.
    if !is_exact(&scored) {
        for (index, first) in single_facts.iter().enumerate() {
            for second in &single_facts[index + 1..] {
                for condition in [and(first, second), or(first, second)] {
                    scored.push((error(&condition), condition));
                }
            }
        }
    }
    if !is_exact(&scored) {
        for first in &single_facts {
            for (index, second) in single_facts.iter().enumerate() {
                for third in &single_facts[index + 1..] {
                    if first == second || first == third {
                        continue;
                    }
                    for condition in [
                        or(first, &and(second, third)),
                        and(first, &or(second, third)),
                    ] {
                        scored.push((error(&condition), condition));
                    }
                }
            }
        }
    }

    // A condition must also miss less than saying nothing would: claiming
    // that `to_match` never happens misses all of it, and claiming that it
    // always happens misses everything else.
    let says_nothing = layouts
        .weight(to_match)
        .min(layouts.weight(layouts.all.difference(to_match)));
    let max_error = ((MAX_CONDITION_ERROR * DEAL_COUNT as f64) as u64)
        .min(says_nothing.saturating_sub(1));
    let tolerance = (SIMPLICITY_TOLERANCE * DEAL_COUNT as f64) as u64;
    let least = scored.iter().map(|(error, _)| *error).min()?;
    if least > max_error {
        return None;
    }
    scored
        .into_iter()
        .filter(|(error, _)| *error <= max_error.min(least + tolerance))
        .min_by_key(|(error, condition)| (condition.size(), *error))
        .map(|(error, condition)| (condition, error))
}

fn and(left: &LayoutCondition, right: &LayoutCondition) -> LayoutCondition {
    LayoutCondition::And(Box::new(left.clone()), Box::new(right.clone()))
}

fn or(left: &LayoutCondition, right: &LayoutCondition) -> LayoutCondition {
    LayoutCondition::Or(Box::new(left.clone()), Box::new(right.clone()))
}

/// The layouts where `fact` holds, with `onside` the defender the line's
/// finesses need to hold the honors.
fn fact_layouts(
    layouts: &Layouts,
    onside: Option<Defender>,
    fact: Fact,
) -> LayoutSet {
    let other = |defender: Defender| match defender {
        Defender::West => Defender::East,
        Defender::East => Defender::West,
    };
    let mut set = LayoutSet::EMPTY;
    for layout in layouts.all.indices() {
        let holds = match fact {
            Fact::Onside { group, all } | Fact::Offside { group, all } => {
                let onside = onside.expect("these facts need a defender");
                let defender = if matches!(fact, Fact::Onside { .. }) {
                    onside
                } else {
                    other(onside)
                };
                let count = layouts.count_of(defender, group, layout);
                if all {
                    count == layouts.groups[group].size()
                } else {
                    count > 0
                }
            }
            Fact::EvenSplit => {
                let west = layouts.length_of(Defender::West, layout);
                let east = layouts.length_of(Defender::East, layout);
                west.abs_diff(east) <= 1
            }
            Fact::Short {
                group,
                length,
                holder,
            } => {
                let defenders = match (holder, onside) {
                    (Holder::Onside, Some(onside)) => vec![onside],
                    (Holder::Offside, Some(onside)) => vec![other(onside)],
                    _ => vec![Defender::West, Defender::East],
                };
                defenders.into_iter().any(|defender| {
                    layouts.count_of(defender, group, layout) == 1
                        && layouts.length_of(defender, layout) <= length
                })
            }
            Fact::HoldsAll(defender) => {
                layouts.length_of(defender, layout) == layouts.missing_count()
            }
        };
        if holds {
            set.insert(layout);
        }
    }
    set
}

/// The condition in words, such as "the K or J is onside".
fn layout_condition_words(
    layouts: &Layouts,
    facts: &[Fact],
    condition: &LayoutCondition,
) -> String {
    let card = |group: usize| rank_symbol(layouts.groups[group].top());
    // A single honor that one side must hold, with that side's name.
    let single_honor = |condition: &LayoutCondition| match condition {
        LayoutCondition::Fact(index) => match facts[*index] {
            Fact::Onside { group, .. } if layouts.groups[group].size() == 1 => {
                Some((group, "onside"))
            }
            Fact::Offside { group, .. }
                if layouts.groups[group].size() == 1 =>
            {
                Some((group, "offside"))
            }
            _ => None,
        },
        _ => None,
    };
    // A group of equal honors, such as the K and Q, one of which one side
    // must hold.
    let group_either = |condition: &LayoutCondition| match condition {
        LayoutCondition::Fact(index) => match facts[*index] {
            Fact::Onside { group, all: false }
                if layouts.groups[group].size() > 1 =>
            {
                Some((group, "onside"))
            }
            Fact::Offside { group, all: false }
                if layouts.groups[group].size() > 1 =>
            {
                Some((group, "offside"))
            }
            _ => None,
        },
        _ => None,
    };
    match condition {
        LayoutCondition::Or(left, right) => {
            if let (Some((first, side)), Some((second, second_side))) =
                (single_honor(left), single_honor(right))
                && side == second_side
            {
                return format!(
                    "the {} or {} is {side}",
                    card(first),
                    card(second)
                );
            }
            if let (Some((first, side)), LayoutCondition::And(middle, last)) =
                (single_honor(left), right.as_ref())
                && let (Some((second, middle_side)), Some((third, last_side))) =
                    (single_honor(middle), single_honor(last))
                && side == middle_side
                && side == last_side
            {
                return format!(
                    "the {} is {side}, or the {} and {} both are",
                    card(first),
                    card(second),
                    card(third)
                );
            }
        }
        LayoutCondition::And(left, right) => {
            // One of a pair of equal honors on each side.
            if let (Some((first, side)), Some((second, second_side))) =
                (group_either(left), group_either(right))
                && first == second
                && side != second_side
                && layouts.groups[first].size() == 2
            {
                let cards: Vec<String> = layouts.groups[first]
                    .ranks
                    .descending()
                    .map(|rank| rank_symbol(rank).to_string())
                    .collect();
                return format!("the {} are split", cards.join(" and "));
            }
            let pairing = match (single_honor(left), group_either(right)) {
                (Some(first), Some(group)) => Some((first, group)),
                _ => single_honor(right).zip(group_either(left)),
            };
            if let Some(((first, side), (group, second_side))) = pairing
                && side == second_side
            {
                return format!(
                    "the {} and either {} are {side}",
                    card(first),
                    alternatives_words(layouts, group)
                );
            }
            if let (Some((first, side)), Some((second, second_side))) =
                (single_honor(left), single_honor(right))
                && side == second_side
            {
                return format!(
                    "the {} and {} are both {side}",
                    card(first),
                    card(second)
                );
            }
            if let Some((first, side)) = single_honor(left)
                && let LayoutCondition::Or(middle, last) = right.as_ref()
                && let (Some((second, middle_side)), Some((third, last_side))) =
                    (single_honor(middle), single_honor(last))
                && side == middle_side
                && side == last_side
            {
                return format!(
                    "the {} and either the {} or {} are {side}",
                    card(first),
                    card(second),
                    card(third)
                );
            }
        }
        LayoutCondition::Fact(_) => {}
    }
    let words = |condition: &LayoutCondition| {
        layout_condition_words(layouts, facts, condition)
    };
    match condition {
        LayoutCondition::Fact(index) => fact_words(layouts, facts[*index]),
        // "Either" marks where the alternatives start, which a comma alone
        // leaves open.
        LayoutCondition::And(left, right) => match right.as_ref() {
            LayoutCondition::Or(first, second) => format!(
                "{}, and either {} or {}",
                words(left),
                words(first),
                words(second)
            ),
            _ => format!("{} and {}", words(left), words(right)),
        },
        LayoutCondition::Or(left, right) => {
            format!("{}, or {}", words(left), words(right))
        }
    }
}

/// A fact in words, such as "the K is onside".
fn fact_words(layouts: &Layouts, fact: Fact) -> String {
    match fact {
        Fact::Onside { group, all } | Fact::Offside { group, all } => {
            let side = if matches!(fact, Fact::Onside { .. }) {
                "onside"
            } else {
                "offside"
            };
            let cards: Vec<String> = layouts.groups[group]
                .ranks
                .descending()
                .map(|rank| rank_symbol(rank).to_string())
                .collect();
            if cards.len() == 1 {
                format!("the {} is {side}", cards[0])
            } else if !all {
                format!("{} is {side}", alternatives_words(layouts, group))
            } else {
                let quantity = if cards.len() == 2 { "both" } else { "all" };
                format!("the {} are {quantity} {side}", cards.join(" and "))
            }
        }
        Fact::EvenSplit => {
            let missing = layouts.missing_count();
            format!("the suit splits {}-{}", missing.div_ceil(2), missing / 2)
        }
        Fact::Short {
            group,
            length,
            holder,
        } => {
            let card = rank_symbol(layouts.groups[group].top());
            let shortness = match length {
                1 => "singleton",
                _ => "singleton or doubleton",
            };
            let place = match holder {
                Holder::Either => "",
                Holder::Onside => " onside",
                Holder::Offside => " offside",
            };
            format!("the {card} is {shortness}{place}")
        }
        Fact::HoldsAll(defender) => holds_all_words(layouts, defender),
    }
}

/// "West holds all four", or the like.
fn holds_all_words(layouts: &Layouts, defender: Defender) -> String {
    const NUMBERS: [&str; 14] = [
        "none", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen",
    ];
    let name = match defender {
        Defender::West => "West",
        Defender::East => "East",
    };
    let count = NUMBERS[usize::from(layouts.missing_count())];
    format!("{name} holds all {count}")
}

/// A group's cards as alternatives, such as "the K or Q".
fn alternatives_words(layouts: &Layouts, group: usize) -> String {
    let cards: Vec<String> = layouts.groups[group]
        .ranks
        .descending()
        .map(|rank| rank_symbol(rank).to_string())
        .collect();
    format!("the {}", cards.join(" or "))
}

/// The extra chances in `extras`, the layouts where the line wins beyond
/// what its condition says, in words starting with a comma; empty when
/// there are none.
fn extras_words(layouts: &Layouts, extras: LayoutSet) -> String {
    if extras.is_empty() {
        return String::new();
    }
    let named_group_count = layouts.groups.len().saturating_sub(1);
    for length in 1..=2 {
        for group in 0..named_group_count {
            if layouts.groups[group].size() != 1 {
                continue;
            }
            let short = Fact::Short {
                group,
                length,
                holder: Holder::Either,
            };
            if fact_layouts(layouts, None, short).is_superset(extras) {
                let card = rank_symbol(layouts.groups[group].top());
                return match length {
                    1 => format!(
                        ", with a small chance to drop a singleton {card}"
                    ),
                    _ => format!(
                        ", with a small extra chance when the {card} is \
                         singleton or doubleton"
                    ),
                };
            }
        }
    }
    for defender in [Defender::West, Defender::East] {
        let holds_all = fact_layouts(layouts, None, Fact::HoldsAll(defender));
        if holds_all.is_superset(extras) {
            return format!(
                ", with a small extra chance when {}",
                holds_all_words(layouts, defender)
            );
        }
    }
    let percent = percent_of_deals(layouts.weight(extras));
    if percent < 100.0 * SMALL_CHANCE {
        format!(
            ", plus a small extra chance ({percent:.2}%) from rarer layouts"
        )
    } else {
        format!(", plus {percent:.2}% more from other layouts")
    }
}
