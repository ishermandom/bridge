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
        "Finesse hoping the K is singleton or doubleton onside, or the T is \
         singleton offside"
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
    // The line cashes its top cards unless someone shows out, so its
    // usual path takes no finesse.
    assert_eq!(
        remark("KQ964-A852@5"),
        "Play for the drop; it fails only when East holds all four"
    );
}

#[test]
fn remark_names_no_condition_that_misses_as_much_as_saying_nothing() {
    // The line wins 5.17% of the time; "West holds all seven" holds in almost
    // none of those layouts, so naming it explains nothing.
    assert_eq!(remark("AKT9-xx@4"), "Finesse");
}

#[test]
fn remark_adds_no_extra_chance_without_a_condition() {
    assert_eq!(remark("AT9-Qxx@3"), "A two-way finesse");
}

#[test]
fn remark_names_equal_honors_on_both_sides() {
    assert_eq!(
        remark("JT543-A2@3"),
        "Finesse hoping the suit splits 3-3, or the K and Q are split, plus a \
         small extra chance (3.23%) from rarer layouts"
    );
}
