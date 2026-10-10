// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The analyzer's answers for each row of
//! `flashcards/input/suit_combinations.csv`.
//!
//! Each test pins the analyzer's own answer, verified by hand. Where it
//! differs from the row, a comment says how.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The best line's chance of success for `problem`, to two decimal places.
fn success_percent(problem: &str) -> String {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    format!("{:.2}", analysis.success_percent())
}

#[test]
fn aq_opposite_xx_makes_2_tricks_half_the_time() {
    assert_eq!(success_percent("AQ-xx@2"), "50.00");
}

#[test]
fn aqj_opposite_xx_makes_3_tricks_half_the_time() {
    assert_eq!(success_percent("AQJ-xx@3"), "50.00");
}

#[test]
fn aqt_opposite_xx_makes_3_tricks_when_both_honors_are_onside() {
    assert_eq!(success_percent("AQT-xx@3"), "24.00");
}

#[test]
fn aqt_opposite_xx_makes_2_tricks_unless_both_honors_are_offside() {
    assert_eq!(success_percent("AQT-xx@2"), "76.00");
}

#[test]
fn ajt_opposite_xx_makes_2_tricks_unless_both_honors_are_offside() {
    assert_eq!(success_percent("AJT-xx@2"), "76.00");
}

#[test]
fn aq9_opposite_xx_adds_a_chance_with_the_9() {
    assert_eq!(success_percent("AQ9-xx@2"), "63.00");
}

#[test]
fn aj9_opposite_xx_needs_the_t_and_another_honor_onside() {
    assert_eq!(success_percent("AJ9-xx@2"), "37.31");
}

#[test]
fn kx_opposite_xx_makes_1_trick_half_the_time() {
    assert_eq!(success_percent("Kx-xx@1"), "50.00");
}

#[test]
fn kqx_opposite_xxx_makes_2_tricks_half_the_time() {
    assert_eq!(success_percent("KQx-xxx@2"), "50.00");
}

#[test]
fn kqjx_opposite_xxx_adds_a_3_3_split_to_the_finesse() {
    assert_eq!(success_percent("KQJx-xxx@3"), "67.76");
}

#[test]
fn kqt_opposite_xxx_loses_to_a_hold_up_of_the_ace() {
    assert_eq!(success_percent("KQT-xxx@2"), "54.84");
}

#[test]
fn kjt_opposite_xxx_makes_2_tricks_half_the_time() {
    assert_eq!(success_percent("KJT-xxx@2"), "50.00");
}

#[test]
fn axx_opposite_qjt_makes_3_tricks_half_the_time() {
    assert_eq!(success_percent("Axx-QJT@3"), "50.00");
}

#[test]
fn akx_opposite_jtx_adds_a_singleton_queen_to_the_finesse() {
    assert_eq!(success_percent("AKx-JTx@3"), "50.48");
}

#[test]
fn k8xx_opposite_jt9_makes_3_tricks_half_the_time() {
    assert_eq!(success_percent("K8xx-JT9@3"), "50.00");
}

#[test]
fn axx_opposite_kjt_adds_a_singleton_queen_to_the_finesse() {
    assert_eq!(success_percent("Axx-KJT@3"), "50.48");
}

#[test]
fn axx_opposite_kjtx_makes_4_tricks_just_over_half_the_time() {
    assert_eq!(success_percent("Axx-KJTx@4"), "51.21");
}

#[test]
fn aqtx_opposite_j9x_makes_4_tricks_half_the_time() {
    assert_eq!(success_percent("AQTx-J9x@4"), "50.00");
}

#[test]
fn ajtx_opposite_q9x_makes_4_tricks_half_the_time() {
    assert_eq!(success_percent("AJTx-Q9x@4"), "50.00");
}
