// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The analyzer's chances for combinations with published results.
//!
//! The figures come from Wikipedia's "Suit combination" article, which makes
//! the same assumptions as the analyzer, unlimited entries and best defense,
//! and from the help pages of SuitPlay, Jeroen Warmerdam's suit-combination
//! program (https://jeroenwarmerdam.pythonanywhere.com/suitplay/help/).

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The best line's chance of success for `problem`, to two decimal places.
fn success_percent(problem: &str) -> String {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    format!("{:.2}", analysis.success_percent())
}

#[test]
fn a104_opposite_q32_makes_2_tricks_74_percent_of_the_time() {
    // The article gives 74%, and its own breakdown sums to 74.5%.
    assert_eq!(success_percent("AT4-Q32@2"), "74.48");
}

#[test]
fn j10543_opposite_a2_makes_3_tricks_64_6_percent_of_the_time() {
    assert_eq!(success_percent("JT543-A2@3"), "64.60");
}

#[test]
fn j10543_opposite_a2_fails_2_tricks_only_against_kqxxx_with_east() {
    // The article states 90.0%, marked as needing a citation, but also says
    // the line fails only when East holds the K, Q, and three or four more:
    // 5.59% of deals, leaving 94.41%.
    assert_eq!(success_percent("JT543-A2@2"), "94.41");
}

#[test]
fn a1042_opposite_953_makes_2_tricks_58_percent_of_the_time() {
    // The article gives 58%, from the Official Encyclopedia of Bridge's 7th
    // edition, correcting the 51% of earlier editions.
    assert_eq!(success_percent("AT42-953@2"), "57.51");
}

#[test]
fn kq10_opposite_432_makes_2_tricks_54_84_percent_of_the_time() {
    // The article quotes two small extra chances for this target, 0.73% and
    // 0.48%, from the Official Encyclopedia of Bridge, without a total.
    // CCAnalyser also gives the best line 54.84%.
    assert_eq!(success_percent("KQT-432@2"), "54.84");
}

/// The best line's chance of success for `problem`, to four decimal places.
fn precise_success_percent(problem: &str) -> String {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    format!("{:.4}", analysis.success_percent())
}

#[test]
fn aq1098_opposite_5432_matches_suitplay_for_5_tricks() {
    // SuitPlay's help gives 26.5652% for 5 tricks and 82.7826% for 4, for
    // the combination its examples use, AQ1098 opposite 5432.
    assert_eq!(precise_success_percent("AQT98-5432@5"), "26.5652");
}

#[test]
fn aq1098_opposite_5432_matches_suitplay_for_4_tricks() {
    assert_eq!(precise_success_percent("AQT98-5432@4"), "82.7826");
}

#[test]
fn k1084_opposite_q32_beats_the_ten_finesse_for_3_tricks() {
    // The article's ten finesse makes 3 tricks 28.7% of the time; a better
    // line for exactly that target exists.
    assert_eq!(success_percent("KT84-Q32@3"), "31.83");
}
