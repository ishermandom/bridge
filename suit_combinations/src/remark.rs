// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The intuition behind a best line, such as "Finesse hoping the K or J is
//! onside".
//!
//! The approach is set out in `suit_combinations/spec.md` #remarks. In
//! short: the line's finesses name its technique and the defender who must
//! hold the missing honors, and the simplest condition on those honors that
//! matches where the line wins says what it hopes for.

use crate::analysis::BestResult;
use crate::cards::rank_symbol;
use crate::describe::Finesse;
use crate::layout_set::LayoutSet;
use crate::layouts::{DEAL_COUNT, Defender, Layouts};

/// A simple fact about a layout, from which conditions are built.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Atom {
    /// The onside defender holds the group's card, or at least one of its
    /// cards; with `all`, every one of them.
    Onside { group: usize, all: bool },
    /// The defenders' cards split as evenly as they can.
    EvenSplit,
    /// The group's single card lies in a holding of at most `length` cards,
    /// so that it falls under that many top cards.
    Short { group: usize, length: u8 },
}

/// A condition on the layout: an atom, or two conditions joined.
#[derive(Clone, PartialEq, Eq, Debug)]
enum Condition {
    Atom(Atom),
    And(Box<Condition>, Box<Condition>),
    Or(Box<Condition>, Box<Condition>),
}

impl Condition {
    /// How many atoms the condition uses.
    fn size(&self) -> usize {
        match self {
            Condition::Atom(_) => 1,
            Condition::And(left, right) | Condition::Or(left, right) => {
                left.size() + right.size()
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
const SIMPLICITY_TOLERANCE: f64 = 0.02;

/// The intuition behind the best lines in `best`.
pub fn remark(layouts: &Layouts, best: &[BestResult]) -> String {
    let wins = best[0].layouts_by_target[0];
    if wins == layouts.all {
        return "This line succeeds however the cards lie".to_string();
    }

    let finesses: Vec<Finesse> = best[0]
        .line
        .main_path()
        .iter()
        .filter_map(|step| step.finesse)
        .collect();
    let onside = finesses.first().map(|finesse| finesse.onside);
    let atoms = atoms(layouts, onside);
    let condition = simplest_condition(layouts, onside, &atoms, wins);
    let extras = match &condition {
        Some(condition) => {
            wins.difference(condition_layouts(layouts, onside, condition))
        }
        None => wins,
    };
    let extras_words = extras_words(layouts, extras);

    let is_two_way = best.iter().any(|result| {
        let other = result
            .line
            .main_path()
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
        Some(condition) => format!(
            "{technique} hoping {}{extras_words}",
            condition_words(layouts, &condition)
        ),
        None => technique.to_string(),
    }
}

/// The atoms worth trying for a line whose finesses need the `onside`
/// defender, if any, to hold the cards they play against.
fn atoms(layouts: &Layouts, onside: Option<Defender>) -> Vec<Atom> {
    let mut atoms = Vec::new();
    // The lowest group holds the small cards, never worth naming.
    let named_groups = layouts.groups.len().saturating_sub(1);
    if onside.is_some() {
        for group in 0..named_groups {
            atoms.push(Atom::Onside { group, all: false });
            if layouts.groups[group].size() > 1 {
                atoms.push(Atom::Onside { group, all: true });
            }
        }
    }
    atoms.push(Atom::EvenSplit);
    // A short honor dropping is what a line without a finesse hopes for; a
    // finesse mentions it only as a small extra chance.
    if onside.is_some() {
        return atoms;
    }
    for group in 0..named_groups {
        if layouts.groups[group].size() == 1 {
            for length in 1..=2 {
                atoms.push(Atom::Short { group, length });
            }
        }
    }
    atoms
}

/// The simplest condition matching `wins` to within `MAX_CONDITION_ERROR`,
/// preferring a simpler one within `SIMPLICITY_TOLERANCE`, built from
/// up to three of `atoms`, if any comes that close; `onside` is the defender
/// the atoms' honors must lie with.
fn simplest_condition(
    layouts: &Layouts,
    onside: Option<Defender>,
    atoms: &[Atom],
    wins: LayoutSet,
) -> Option<Condition> {
    let mut candidates: Vec<Condition> =
        atoms.iter().map(|&atom| Condition::Atom(atom)).collect();
    let single = candidates.clone();
    for (index, first) in single.iter().enumerate() {
        for second in &single[index + 1..] {
            candidates.push(and(first, second));
            candidates.push(or(first, second));
        }
    }
    for first in &single {
        for (index, second) in single.iter().enumerate() {
            for third in &single[index + 1..] {
                if first == second || first == third {
                    continue;
                }
                candidates.push(or(first, &and(second, third)));
                candidates.push(and(first, &or(second, third)));
            }
        }
    }

    let usable = (MAX_CONDITION_ERROR * DEAL_COUNT as f64) as u64;
    let tolerance = (SIMPLICITY_TOLERANCE * DEAL_COUNT as f64) as u64;
    let error = |condition: &Condition| {
        let matched = condition_layouts(layouts, onside, condition);
        layouts.weight(wins.difference(matched))
            + layouts.weight(matched.difference(wins))
    };
    let scored: Vec<(u64, &Condition)> = candidates
        .iter()
        .map(|condition| (error(condition), condition))
        .collect();
    let least = scored.iter().map(|(error, _)| *error).min()?;
    if least > usable {
        return None;
    }
    scored
        .iter()
        .filter(|(error, _)| *error <= least + tolerance)
        .min_by_key(|(error, condition)| (condition.size(), *error))
        .map(|(_, condition)| (*condition).clone())
}

fn and(left: &Condition, right: &Condition) -> Condition {
    Condition::And(Box::new(left.clone()), Box::new(right.clone()))
}

fn or(left: &Condition, right: &Condition) -> Condition {
    Condition::Or(Box::new(left.clone()), Box::new(right.clone()))
}

/// The layouts where `condition` holds, with `onside` the defender who must
/// hold the honors.
fn condition_layouts(
    layouts: &Layouts,
    onside: Option<Defender>,
    condition: &Condition,
) -> LayoutSet {
    match condition {
        Condition::Atom(atom) => atom_layouts(layouts, onside, *atom),
        Condition::And(left, right) => condition_layouts(layouts, onside, left)
            .intersection(condition_layouts(layouts, onside, right)),
        Condition::Or(left, right) => condition_layouts(layouts, onside, left)
            .union(condition_layouts(layouts, onside, right)),
    }
}

/// The layouts where `atom` holds.
fn atom_layouts(
    layouts: &Layouts,
    onside: Option<Defender>,
    atom: Atom,
) -> LayoutSet {
    let mut set = LayoutSet::EMPTY;
    for layout in layouts.all.indices() {
        let holds = match atom {
            Atom::Onside { group, all } => {
                let defender = onside.expect("onside atoms need a defender");
                let count = layouts.count_of(defender, group, layout);
                if all {
                    count == layouts.groups[group].size()
                } else {
                    count > 0
                }
            }
            Atom::EvenSplit => {
                let west = layouts.length_of(Defender::West, layout);
                let east = layouts.length_of(Defender::East, layout);
                west.abs_diff(east) <= 1
            }
            Atom::Short { group, length } => [Defender::West, Defender::East]
                .into_iter()
                .any(|defender| {
                    layouts.count_of(defender, group, layout) == 1
                        && layouts.length_of(defender, layout) <= length
                }),
        };
        if holds {
            set.insert(layout);
        }
    }
    set
}

/// The condition in words, such as "the K or J is onside".
fn condition_words(layouts: &Layouts, condition: &Condition) -> String {
    let card = |group: usize| rank_symbol(layouts.groups[group].top());
    // Honors that the onside defender must hold one by one.
    let single = |condition: &Condition| match condition {
        Condition::Atom(Atom::Onside { group, .. })
            if layouts.groups[*group].size() == 1 =>
        {
            Some(*group)
        }
        _ => None,
    };
    match condition {
        Condition::Or(left, right) => {
            if let (Some(first), Some(second)) = (single(left), single(right)) {
                return format!(
                    "the {} or {} is onside",
                    card(first),
                    card(second)
                );
            }
            if let (Some(first), Condition::And(middle, last)) =
                (single(left), right.as_ref())
                && let (Some(second), Some(third)) =
                    (single(middle), single(last))
            {
                return format!(
                    "the {} is onside, or the {} and {} both are",
                    card(first),
                    card(second),
                    card(third)
                );
            }
        }
        Condition::And(left, right) => {
            let group_either = |condition: &Condition| match condition {
                Condition::Atom(Atom::Onside { group, all: false })
                    if layouts.groups[*group].size() > 1 =>
                {
                    Some(*group)
                }
                _ => None,
            };
            let pairing = match (single(left), group_either(right)) {
                (Some(first), Some(group)) => Some((first, group)),
                _ => single(right).zip(group_either(left)),
            };
            if let Some((first, group)) = pairing {
                return format!(
                    "the {} and either {} are onside",
                    card(first),
                    either_words(layouts, group)
                );
            }
            if let (Some(first), Some(second)) = (single(left), single(right)) {
                return format!(
                    "the {} and {} are both onside",
                    card(first),
                    card(second)
                );
            }
            if let Some(first) = single(left)
                && let Condition::Or(middle, last) = right.as_ref()
                && let (Some(second), Some(third)) =
                    (single(middle), single(last))
            {
                return format!(
                    "the {} and either the {} or {} are onside",
                    card(first),
                    card(second),
                    card(third)
                );
            }
        }
        Condition::Atom(_) => {}
    }
    match condition {
        Condition::Atom(atom) => atom_words(layouts, *atom),
        Condition::And(left, right) => format!(
            "{}, and {}",
            condition_words(layouts, left),
            condition_words(layouts, right)
        ),
        Condition::Or(left, right) => format!(
            "{}, or {}",
            condition_words(layouts, left),
            condition_words(layouts, right)
        ),
    }
}

/// An atom in words, such as "the K is onside".
fn atom_words(layouts: &Layouts, atom: Atom) -> String {
    match atom {
        Atom::Onside { group, all: false } => {
            if layouts.groups[group].size() == 1 {
                format!(
                    "the {} is onside",
                    rank_symbol(layouts.groups[group].top())
                )
            } else {
                format!("{} is onside", either_words(layouts, group))
            }
        }
        Atom::Onside { group, all: true } => {
            let cards: Vec<String> = layouts.groups[group]
                .ranks
                .descending()
                .map(|rank| rank_symbol(rank).to_string())
                .collect();
            let quantity = if cards.len() == 2 { "both" } else { "all" };
            format!("the {} are {quantity} onside", cards.join(" and "))
        }
        Atom::EvenSplit => {
            let missing = layouts.missing_count();
            format!("the suit splits {}-{}", missing.div_ceil(2), missing / 2)
        }
        Atom::Short { group, length } => {
            let card = rank_symbol(layouts.groups[group].top());
            match length {
                1 => format!("the {card} is singleton"),
                _ => format!("the {card} is singleton or doubleton"),
            }
        }
    }
}

/// A group's cards as alternatives, such as "the K or Q".
fn either_words(layouts: &Layouts, group: usize) -> String {
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
    let named_groups = layouts.groups.len().saturating_sub(1);
    for length in 1..=2 {
        for group in 0..named_groups {
            if layouts.groups[group].size() != 1 {
                continue;
            }
            let short =
                atom_layouts(layouts, None, Atom::Short { group, length });
            if short.is_superset(extras) {
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
    let percent = 100.0 * layouts.weight(extras) as f64 / DEAL_COUNT as f64;
    format!(", plus a small extra chance ({percent:.2}%) from rarer layouts")
}
