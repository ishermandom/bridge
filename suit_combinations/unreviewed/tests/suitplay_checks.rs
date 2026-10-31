// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Combinations whose best chance SuitPlay confirmed to four decimal places,
//! as `suitplay/run.sh` runs SuitPlay. They were chosen where a published
//! table prints a different figure or the best line is hard to find.

use suit_combinations::analysis::best_success_percent;
use suit_combinations::notation::parse_problem;

/// The best chance for `problem`, to four decimal places as SuitPlay shows it.
fn success_percent(problem: &str) -> String {
    let problem = parse_problem(problem).expect("a valid problem");
    format!("{:.4}", best_success_percent(problem))
}

#[test]
fn akt9x_opposite_xxxx_makes_5_tricks_46_percent_of_the_time() {
    assert_eq!(success_percent("AKT9x-xxxx@5"), "46.3478");
}

#[test]
fn aq9x_opposite_xxx_makes_3_tricks_32_percent_of_the_time() {
    assert_eq!(success_percent("AQ9x-xxx@3"), "32.3168");
}

#[test]
fn kqt32_opposite_654_makes_4_tricks_55_percent_of_the_time() {
    assert_eq!(success_percent("KQT32-654@4"), "55.3913");
}

#[test]
fn aj9_opposite_xxx_makes_2_tricks_38_percent_of_the_time() {
    assert_eq!(success_percent("AJ9-xxx@2"), "37.7267");
}

#[test]
fn kt9x_opposite_xxx_makes_a_trick_91_percent_of_the_time() {
    // bridgehands.com's table prints 93%.
    assert_eq!(success_percent("KT9x-xxx@1"), "90.7764");
}

#[test]
fn aj8_opposite_txx_makes_2_tricks_40_percent_of_the_time() {
    // bridgehands.com's table prints 24%.
    assert_eq!(success_percent("AJ8-Txx@2"), "39.6646");
}

#[test]
fn qxxx_opposite_at87_makes_3_tricks_62_percent_of_the_time() {
    // Warmerdam's corrections to the Official Encyclopedia of Bridge print
    // 62.6087%.
    assert_eq!(success_percent("Qxxx-AT87@3"), "61.6087");
}

#[test]
fn akjtxx_opposite_a_void_makes_5_tricks_71_percent_of_the_time() {
    assert_eq!(success_percent("AKJTxx-(void)@5"), "70.8944");
}
