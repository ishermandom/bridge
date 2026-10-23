// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Lines that follow second hand only where the line can still succeed, as
//! `suit_combinations/spec.md` #describing-lines describes.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The best line in words for `problem`, such as `AQ-xx@2`.
fn line(problem: &str) -> String {
    analyze(parse_problem(problem).expect("a valid problem")).line_words()
}

#[test]
fn line_ignores_low_cards_held_only_where_it_fails() {
    // 4 tricks need East's K to be singleton, so East never has a low card to
    // play where the line can win: the A drops the K, and two finesses
    // against West's J and 9 follow.
    assert_eq!(
        line("QT85-A742@4"),
        "Cash the A, then low to the 8, then low to the T"
    );
}

#[test]
fn line_answers_a_show_out_with_its_own_card() {
    // When West shows out, the Q still makes 2 tricks, so the line plays it
    // rather than the A, and has nothing left to say.
    assert_eq!(line("AQJ-xx@2"), "Low to the Q");
}
