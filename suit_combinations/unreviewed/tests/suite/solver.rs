// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The search for declarer's best strategy: the chances of well-known
//! plays, and the one card the search tries from each run of equivalent
//! cards.

use suit_combinations::cards::{RankSet, rank_for_symbol};
use suit_combinations::layouts::{DEAL_COUNT, Layouts};
use suit_combinations::notation::parse_problem;
use suit_combinations::solver::{Position, Solver};

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
fn distinct_plays_keep_one_card_per_equivalent_set() {
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
        solver.distinct_plays(start, layouts.combination.north, RankSet::EMPTY),
        vec![
            rank_for_symbol('A').unwrap(),
            rank_for_symbol('T').unwrap(),
            layouts.combination.north.lowest().unwrap(),
        ]
    );
}
