// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Remarks that need more than an honor lying onside, as
//! `suit_combinations/spec.md` #remarks describes.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The remark for `problem`, such as `AQ-xx@2`.
fn remark(problem: &str) -> String {
    analyze(parse_problem(problem).expect("a valid problem")).remark()
}

#[test]
fn remark_names_where_a_short_honor_must_lie() {
    assert_eq!(
        remark("AQxxx-J9xx@5"),
        "Repeated finesse hoping the K is singleton or doubleton onside, or \
         the T is singleton offside"
    );
}

#[test]
fn remark_names_a_drop_and_a_one_sided_split() {
    assert_eq!(
        remark("AKJT9-xxxx@5"),
        "Play for the drop hoping the Q is singleton or doubleton, with a \
         small extra chance when West holds all four"
    );
}

#[test]
fn remark_marks_where_alternatives_start() {
    assert_eq!(
        remark("AQT98-5432@5"),
        "Repeated finesse hoping the K is onside, and either the suit splits \
         2-2 or the J is singleton offside"
    );
}

#[test]
fn remark_plays_for_an_even_split_without_a_finesse() {
    assert_eq!(remark("AKxxx-xxx@4"), "Play for a 3-2 split");
}

#[test]
fn remark_says_when_a_likely_line_fails() {
    assert_eq!(
        remark("KQ964-A852@5"),
        "Finesse; it fails only when East holds all four"
    );
}

#[test]
fn remark_names_equal_honors_on_both_sides() {
    assert_eq!(
        remark("AQ8x-K9xx@4"),
        "Finesse hoping the suit splits 3-2, or the J and T are split"
    );
}
