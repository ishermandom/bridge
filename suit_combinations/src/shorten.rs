// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Shortening a complete line without leaving anything out.
//!
//! Each rewrite is kept only if the line still passes `crate::check`, which
//! reads it the way a reader would, so a shortened line stays as complete as
//! the one it came from. The rewrites are set out in
//! `suit_combinations/spec.md` #shortening-lines.

use std::cmp::Reverse;

use crate::check;
use crate::describe::{Condition, Line, condition_words};
use crate::layout_set::LayoutSet;
use crate::layouts::Layouts;
use crate::solver::Solver;

/// One move from a line's start toward one of its nodes: past a step to the
/// rest of the line, or into one of a split's parts.
#[derive(Clone, Copy, Debug)]
enum Turn {
    Rest,
    Part(usize),
}

/// Which part of a split `shorten` makes "Otherwise".
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum OtherwiseRule {
    /// The usual case, the part a teacher would leave unstated: the one
    /// holding the most deals in which declarer played the card the trick is
    /// named by.
    Usual,
    /// Whichever part, as "Otherwise", removes the most other parts.
    FewestParts,
}

/// `line`, shortened by every rewrite that keeps it passing `check` for
/// `required`, choosing each split's "Otherwise" by `rule`; `line` itself if
/// it doesn't pass to begin with.
pub(crate) fn shorten(
    solver: &mut Solver,
    mut line: Line,
    required: &[LayoutSet],
    rule: OtherwiseRule,
) -> Line {
    if check::check(solver, &line, required).is_err() {
        return line;
    }
    let layouts = solver.layouts;
    let mut keeps =
        |candidate: &Line| check::check(solver, candidate, required).is_ok();
    let mut pending: Vec<Vec<Turn>> = vec![Vec::new()];
    while let Some(path) = pending.pop() {
        match node(&line, &path) {
            Line::Done => {}
            Line::Play(step, _) => {
                // An answer the line doesn't need is one fewer to read.
                for index in (0..step.exceptions.len()).rev() {
                    let mut candidate = line.clone();
                    if let Line::Play(step, _) = node_mut(&mut candidate, &path)
                    {
                        step.exceptions.remove(index);
                    }
                    if keeps(&candidate) {
                        line = candidate;
                    }
                }
                pending.push(with(&path, Turn::Rest));
            }
            Line::Split(_) => {
                line = shorten_split(line, &path, layouts, rule, &mut keeps);
                match node(&line, &path) {
                    // A split that became one line is shortened as that line.
                    Line::Split(parts) => {
                        for index in 0..parts.len() {
                            pending.push(with(&path, Turn::Part(index)));
                        }
                    }
                    _ => pending.push(path),
                }
            }
        }
    }
    line
}

/// `line` with the split at `path` shortened. A part chosen by `rule`
/// becomes "Otherwise" where the line still passes that way; then every
/// other part whose branches the "Otherwise" line also wins is removed; and
/// once only "Otherwise" is left, the split becomes that part's line.
fn shorten_split(
    line: Line,
    path: &[Turn],
    layouts: &Layouts,
    rule: OtherwiseRule,
    keeps: &mut impl FnMut(&Line) -> bool,
) -> Line {
    let Line::Split(parts) = node(&line, path) else {
        return line;
    };
    let has_otherwise = parts
        .iter()
        .any(|part| part.condition == Condition::Otherwise);
    if has_otherwise || parts.len() < 2 {
        return drop_into_otherwise(line, path, keeps);
    }
    // A teacher states the unusual cases and leaves the usual one, the trick
    // played as named, as "Otherwise"; among parts that take as many deals
    // that way, the one with the longest condition saves the most.
    let mut order: Vec<usize> = (0..parts.len()).collect();
    order.sort_by_key(|&index| {
        let part = &parts[index];
        (
            Reverse(part.named_weight),
            Reverse(condition_words(&part.condition, layouts).len()),
        )
    });
    // For the fewest parts, any part might be the one that lets the most
    // others go, so each is tried in that order, up to a few, keeping the
    // first among those that leave the fewest.
    let mut fewest: Option<Line> = None;
    for index in order.into_iter().take(OTHERWISE_TRIES) {
        let mut candidate = line.clone();
        if let Line::Split(parts) = node_mut(&mut candidate, path) {
            let mut part = parts.remove(index);
            part.condition = Condition::Otherwise;
            parts.push(part);
        }
        if !keeps(&candidate) {
            continue;
        }
        let candidate = drop_into_otherwise(candidate, path, keeps);
        // The usual case is the first in that order that the line can leave
        // as "Otherwise".
        if rule == OtherwiseRule::Usual {
            return candidate;
        }
        let is_fewer = fewest.as_ref().is_none_or(|fewest| {
            parts_len(&candidate, path) < parts_len(fewest, path)
        });
        if is_fewer {
            fewest = Some(candidate);
        }
    }
    fewest.unwrap_or(line)
}

/// How many of a split's parts `shorten_split` tries as "Otherwise", which
/// keeps a split with many parts quick.
const OTHERWISE_TRIES: usize = 6;

/// `line` with each part of the split at `path` dropped that its
/// "Otherwise" part can take, and the split replaced by its "Otherwise" line
/// once that's all that's left.
fn drop_into_otherwise(
    mut line: Line,
    path: &[Turn],
    keeps: &mut impl FnMut(&Line) -> bool,
) -> Line {
    let Line::Split(parts) = node(&line, path) else {
        return line;
    };
    let is_otherwise_last = parts
        .last()
        .is_some_and(|part| part.condition == Condition::Otherwise);
    if !is_otherwise_last {
        return line;
    }
    // Every part but the last, which is "Otherwise".
    for index in (0..parts_len(&line, path) - 1).rev() {
        let mut candidate = line.clone();
        if let Line::Split(parts) = node_mut(&mut candidate, path) {
            let dropped = parts.remove(index);
            // The dropped part's deals now follow the "Otherwise" line.
            let otherwise = parts.last_mut().expect("the \"Otherwise\" part");
            otherwise.weight += dropped.weight;
            otherwise.named_weight += dropped.named_weight;
        }
        if keeps(&candidate) {
            line = candidate;
        }
    }
    if parts_len(&line, path) == 1 {
        let mut candidate = line.clone();
        let target = node_mut(&mut candidate, path);
        if let Line::Split(parts) = target {
            let only = parts.remove(0).line;
            *target = only;
        }
        if keeps(&candidate) {
            line = candidate;
        }
    }
    line
}

/// The number of parts in the split at `path`, or 0 when the node there
/// isn't a split.
fn parts_len(line: &Line, path: &[Turn]) -> usize {
    match node(line, path) {
        Line::Split(parts) => parts.len(),
        _ => 0,
    }
}

/// `path` with `turn` added.
fn with(path: &[Turn], turn: Turn) -> Vec<Turn> {
    let mut longer = path.to_vec();
    longer.push(turn);
    longer
}

/// The node of `line` that `path` leads to.
fn node<'l>(line: &'l Line, path: &[Turn]) -> &'l Line {
    let mut node = line;
    for turn in path {
        node = match (node, turn) {
            (Line::Play(_, rest), Turn::Rest) => rest,
            (Line::Split(parts), Turn::Part(index)) => &parts[*index].line,
            _ => unreachable!("a path follows the line's own shape"),
        };
    }
    node
}

/// The node of `line` that `path` leads to, to change.
fn node_mut<'l>(line: &'l mut Line, path: &[Turn]) -> &'l mut Line {
    let mut node = line;
    for turn in path {
        node = match (node, turn) {
            (Line::Play(_, rest), Turn::Rest) => rest,
            (Line::Split(parts), Turn::Part(index)) => &mut parts[*index].line,
            _ => unreachable!("a path follows the line's own shape"),
        };
    }
    node
}
