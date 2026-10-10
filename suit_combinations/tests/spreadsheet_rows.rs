// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The analyzer's answers for each row of
//! `flashcards/input/suit_combinations.csv`.
//!
//! Each test pins the analyzer's own answer, verified by hand. Where it
//! differs from the row, a comment says how.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The analyzer's answer for one problem.
#[derive(Debug, PartialEq)]
struct Answer {
    /// The best line's chance of success, to two decimal places.
    success_percent: String,
    /// The best line in words.
    line: String,
}

/// The analyzer's answer for `problem`, such as `AQ-xx@2`.
fn answer(problem: &str) -> Answer {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    Answer {
        success_percent: format!("{:.2}", analysis.success_percent()),
        line: analysis.line_words(),
    }
}

#[test]
fn aq_opposite_xx_makes_2_tricks_half_the_time() {
    assert_eq!(
        answer("AQ-xx@2"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the Q".to_string(),
        }
    );
}

#[test]
fn aqj_opposite_xx_makes_3_tricks_half_the_time() {
    assert_eq!(
        answer("AQJ-xx@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the Q, then low to the J".to_string(),
        }
    );
}

#[test]
fn aqt_opposite_xx_makes_3_tricks_when_both_honors_are_onside() {
    assert_eq!(
        answer("AQT-xx@3"),
        Answer {
            success_percent: "24.00".to_string(),
            line: "Low to the T, then low to the Q".to_string(),
        }
    );
}

#[test]
fn aqt_opposite_xx_makes_2_tricks_unless_both_honors_are_offside() {
    assert_eq!(
        answer("AQT-xx@2"),
        Answer {
            success_percent: "76.00".to_string(),
            line: "Low to the T, then low to the Q".to_string(),
        }
    );
}

#[test]
fn ajt_opposite_xx_makes_2_tricks_unless_both_honors_are_offside() {
    assert_eq!(
        answer("AJT-xx@2"),
        Answer {
            success_percent: "76.00".to_string(),
            line: "Low to the J, then low to the T".to_string(),
        }
    );
}

#[test]
fn aq9_opposite_xx_adds_a_chance_with_the_9() {
    assert_eq!(
        answer("AQ9-xx@2"),
        Answer {
            success_percent: "63.00".to_string(),
            line: "Low to the 9, then low to the Q".to_string(),
        }
    );
}

#[test]
fn aj9_opposite_xx_needs_the_t_and_another_honor_onside() {
    assert_eq!(
        answer("AJ9-xx@2"),
        Answer {
            success_percent: "37.31".to_string(),
            line: "Low to the 9, then low to the J".to_string(),
        }
    );
}

#[test]
fn kx_opposite_xx_makes_1_trick_half_the_time() {
    assert_eq!(
        answer("Kx-xx@1"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the K".to_string(),
        }
    );
}

#[test]
fn kqx_opposite_xxx_makes_2_tricks_half_the_time() {
    assert_eq!(
        answer("KQx-xxx@2"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the K, then low to the Q".to_string(),
        }
    );
}

#[test]
fn kqjx_opposite_xxx_adds_a_3_3_split_to_the_finesse() {
    assert_eq!(
        answer("KQJx-xxx@3"),
        Answer {
            success_percent: "67.76".to_string(),
            line: "Low to the K, then low to the Q, then low to the J"
                .to_string(),
        }
    );
}

#[test]
fn kqt_opposite_xxx_loses_to_a_hold_up_of_the_ace() {
    // The row finesses the T once the K loses. Cashing the Q works as well:
    // the J only matters when it is short with West, so it falls.
    assert_eq!(
        answer("KQT-xxx@2"),
        Answer {
            success_percent: "54.84".to_string(),
            line: "Low to the K, then low to the Q".to_string(),
        }
    );
}

#[test]
fn kjt_opposite_xxx_makes_2_tricks_half_the_time() {
    assert_eq!(
        answer("KJT-xxx@2"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the J, then low to the T".to_string(),
        }
    );
}

#[test]
fn axx_opposite_qjt_makes_3_tricks_half_the_time() {
    // The row stops after the first trick.
    assert_eq!(
        answer("Axx-QJT@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the Q, then run the J".to_string(),
        }
    );
}

#[test]
fn akx_opposite_jtx_adds_a_singleton_queen_to_the_finesse() {
    assert_eq!(
        answer("AKx-JTx@3"),
        Answer {
            success_percent: "50.48".to_string(),
            line: "Cash the A, then run the J".to_string(),
        }
    );
}

#[test]
fn k8xx_opposite_jt9_makes_3_tricks_half_the_time() {
    // The row stops after the first trick.
    assert_eq!(
        answer("K8xx-JT9@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the J, then run the T, then run the 9".to_string(),
        }
    );
}

#[test]
fn axx_opposite_kjt_is_a_two_way_finesse() {
    assert_eq!(
        answer("Axx-KJT@3"),
        Answer {
            success_percent: "50.48".to_string(),
            line: "Either:\n\
                   * Cash the A, then low to the J\n\
                   * Cash the K, then run the J"
                .to_string(),
        }
    );
}

#[test]
fn axx_opposite_kjtx_makes_4_tricks_just_over_half_the_time() {
    // The row stops after the second trick.
    assert_eq!(
        answer("Axx-KJTx@4"),
        Answer {
            success_percent: "51.21".to_string(),
            line: "Cash the A, then low to the J, then low to the T"
                .to_string(),
        }
    );
}

#[test]
fn aqtx_opposite_j9x_makes_4_tricks_half_the_time() {
    // The row stops after the second trick.
    assert_eq!(
        answer("AQTx-J9x@4"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the 9, then run the J, then low to the Q".to_string(),
        }
    );
}

#[test]
fn ajtx_opposite_q9x_makes_4_tricks_half_the_time() {
    // The row stops after the second trick.
    assert_eq!(
        answer("AJTx-Q9x@4"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the 9, then run the Q, then low to the J".to_string(),
        }
    );
}
