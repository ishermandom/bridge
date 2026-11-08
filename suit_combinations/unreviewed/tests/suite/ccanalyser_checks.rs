// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Harder combinations whose best chance
//! [CCAnalyser](https://bridge.esmarkkappel.dk/main/main.html) confirmed
//! exactly, with its default options: South on lead, unlimited entries, and
//! nothing known about the defenders' hands.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The best line's chance of success for `problem`, to two decimal places.
fn success_percent(problem: &str) -> String {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    format!("{:.2}", analysis.success_percent())
}

#[test]
fn kjxx_opposite_a9xx_always_makes_3_tricks() {
    assert_eq!(success_percent("KJxx-A9xx@3"), "100.00");
}

#[test]
fn aqxxx_opposite_j9xx_makes_5_tricks_a_third_of_the_time() {
    assert_eq!(success_percent("AQxxx-J9xx@5"), "32.78");
}

#[test]
fn aq8xx_opposite_j9xx_always_makes_4_tricks() {
    assert_eq!(success_percent("AQ8xx-J9xx@4"), "100.00");
}

#[test]
fn kqxxx_opposite_at9x_always_makes_5_tricks() {
    assert_eq!(success_percent("KQxxx-AT9x@5"), "100.00");
}

#[test]
fn kt84_opposite_q32_makes_2_tricks_86_percent_of_the_time() {
    assert_eq!(success_percent("KT84-Q32@2"), "85.93");
}
