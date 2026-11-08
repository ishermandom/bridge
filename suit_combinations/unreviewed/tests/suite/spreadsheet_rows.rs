// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The analyzer's answers for each row of
//! `flashcards/input/suit_combinations.csv`.
//!
//! Each test pins the analyzer's own answer, verified by hand. Where it
//! differs from the row beyond wording, a comment says how.

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

/// The analyzer's answer for one problem.
#[derive(Debug, PartialEq)]
struct Answer {
    /// The best line's chance of success, to two decimal places.
    success_percent: String,
    /// The best line in words.
    line: String,
    /// The intuition behind the line.
    remark: String,
}

/// The analyzer's answer for `problem`, such as `AQ-xx@2`.
fn answer(problem: &str) -> Answer {
    let analysis = analyze(parse_problem(problem).expect("a valid problem"));
    Answer {
        success_percent: format!("{:.2}", analysis.success_percent()),
        line: analysis.line_words(),
        remark: analysis.remark(),
    }
}

#[test]
fn aq_opposite_xx_makes_2_tricks_half_the_time() {
    assert_eq!(
        answer("AQ-xx@2"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the Q".to_string(),
            remark: "Finesse hoping the K is onside".to_string(),
        }
    );
}

#[test]
fn aqj_opposite_xx_makes_3_tricks_half_the_time() {
    // The row calls this a finesse, not a repeated one.
    assert_eq!(
        answer("AQJ-xx@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the Q, then low to the J".to_string(),
            remark: "Repeated finesse hoping the K is onside".to_string(),
        }
    );
}

#[test]
fn aqt_opposite_xx_makes_3_tricks_when_both_honors_are_onside() {
    // The row's "Low to the T, then low to the Q" leaves out West playing
    // the K or the J, after which North wins as cheaply as it can and
    // finesses the T again.
    assert_eq!(
        answer("AQT-xx@3"),
        Answer {
            success_percent: "24.00".to_string(),
            line: "Low to the T. If West plays the K or the J, low to the T. \
                   Otherwise, low to the Q."
                .to_string(),
            remark: "Finesse hoping the K and J are both onside".to_string(),
        }
    );
}

#[test]
fn aqt_opposite_xx_makes_2_tricks_unless_both_honors_are_offside() {
    // The row adds that the first finesse makes a third trick when both
    // honors are onside.
    assert_eq!(
        answer("AQT-xx@2"),
        Answer {
            success_percent: "76.00".to_string(),
            line: "Low to the T, then low to the Q".to_string(),
            remark: "Finesse hoping the K or J is onside".to_string(),
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
            remark: "Finesse hoping the K or Q is onside".to_string(),
        }
    );
}

#[test]
fn aq9_opposite_xx_adds_a_chance_with_the_9() {
    // The row's "Low to the 9, then low to the Q" leaves out West playing
    // the J or the T, after which the Q wins and North finesses the 9 again.
    assert_eq!(
        answer("AQ9-xx@2"),
        Answer {
            success_percent: "63.00".to_string(),
            line: "Low to the 9. If West plays the J or the T, low to the 9. \
                   Otherwise, low to the Q."
                .to_string(),
            remark: "Finesse hoping the K is onside, or the J and T are both \
                    onside"
                .to_string(),
        }
    );
}

#[test]
fn aj9_opposite_xx_needs_the_t_and_another_honor_onside() {
    // The extra chance is West holding the K and Q alone, which fall under
    // the A and J. The row adds a tip on which cases to consider. Its "Low
    // to the 9, then low to the J" leaves out West playing the K, the Q or
    // the T, after which North finesses the 9 again.
    assert_eq!(
        answer("AJ9-xx@2"),
        Answer {
            success_percent: "37.31".to_string(),
            line: "Low to the 9. If West plays the K, the Q or the T, low to \
                   the 9. Otherwise, low to the J."
                .to_string(),
            remark: "Finesse hoping the T and either the K or Q are onside, \
                    plus a small extra chance (0.31%) from rarer layouts"
                .to_string(),
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
            remark: "Finesse hoping the A is onside".to_string(),
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
            remark: "Repeated finesse hoping the A is onside".to_string(),
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
            remark: "Repeated finesse hoping the A is onside, or the suit \
                    splits 3-3"
                .to_string(),
        }
    );
}

#[test]
fn kqt_opposite_xxx_finesses_twice_with_a_small_chance_from_the_j() {
    // The row finesses the T once the K loses. Cashing the Q works as well:
    // the J only matters when it is short with West, so it falls. The row's
    // remark also hopes for the J with West whenever the A is with East, but
    // East can hold up the A and leave declarer guessing.
    assert_eq!(
        answer("KQT-xxx@2"),
        Answer {
            success_percent: "54.84".to_string(),
            line: "Low to the K, then low to the Q".to_string(),
            remark: "Repeated finesse hoping the A is onside, with a small \
                    extra chance when the J is singleton or doubleton"
                .to_string(),
        }
    );
}

#[test]
fn kjt_opposite_xxx_makes_2_tricks_half_the_time() {
    // The J and T take the same tricks, so either can be finessed first.
    assert_eq!(
        answer("KJT-xxx@2"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Low to the T, then low to the J".to_string(),
            remark: "Repeated finesse hoping the Q is onside".to_string(),
        }
    );
}

#[test]
fn axx_opposite_qjt_makes_3_tricks_half_the_time() {
    assert_eq!(
        answer("Axx-QJT@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the Q".to_string(),
            remark: "Repeated finesse hoping the K is onside".to_string(),
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
            remark: "Finesse hoping the Q is onside, with a small chance to \
                    drop a singleton Q"
                .to_string(),
        }
    );
}

#[test]
fn k8xx_opposite_jt9_makes_3_tricks_half_the_time() {
    // The row's "Run the J" leaves out what follows West covering, or the A
    // falling.
    assert_eq!(
        answer("K8xx-JT9@3"),
        Answer {
            success_percent: "50.00".to_string(),
            line: "Run the J.\n\
                   - If West plays the Q, low to the T, then run the 9.\n\
                   - Otherwise:\n  \
                   - If West plays a low card and East plays a low card, run \
                   the T, then run the 9 (if West shows out, play low).\n  \
                   - Otherwise, run the T."
                .to_string(),
            remark: "Repeated finesse hoping the Q is onside".to_string(),
        }
    );
}

#[test]
fn axx_opposite_kjt_is_a_two_way_finesse() {
    // The row adds advice on getting the defenders to lead the suit.
    assert_eq!(
        answer("Axx-KJT@3"),
        Answer {
            success_percent: "50.48".to_string(),
            line: "Either:\n* Cash the A, then low to the J\n* Cash the K, \
                  then run the J"
                .to_string(),
            remark: "A two-way finesse, with a small chance to drop a \
                    singleton Q"
                .to_string(),
        }
    );
}

#[test]
fn axx_opposite_kjtx_makes_4_tricks_just_over_half_the_time() {
    // The row stops after the second trick, and its remark explains why
    // finessing toward the J beats running it.
    assert_eq!(
        answer("Axx-KJTx@4"),
        Answer {
            success_percent: "51.21".to_string(),
            line: "Cash the A, then low to the J, then low to the T"
                .to_string(),
            remark: "Repeated finesse hoping the Q is onside, with a small \
                    chance to drop a singleton Q"
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
            remark: "Repeated finesse hoping the K is onside".to_string(),
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
            remark: "Repeated finesse hoping the K is onside".to_string(),
        }
    );
}
