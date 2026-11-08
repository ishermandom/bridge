// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Comparing the analyzer's chances with SuitPlay's printed results:
//! agreement, targets outside the listed ones, and lines that are flagged,
//! reported as errors, or unreadable.

use suit_combinations::suitplay_comparison::{
    HoldingComparison, Outcome, TargetComparison, compare_with_suitplay,
    suitplay_report,
};

/// The comparisons for SuitPlay results given as `text`.
fn compare_text(text: &str) -> Vec<HoldingComparison> {
    compare_with_suitplay(text.as_bytes()).expect("comparable results")
}

/// The single holding's target comparisons in `comparisons`.
fn only_targets(comparisons: Vec<HoldingComparison>) -> Vec<TargetComparison> {
    let [comparison] = comparisons.try_into().expect("one holding");
    match comparison.outcome {
        Outcome::Targets(targets) => targets,
        other => panic!("not compared: {other:?}"),
    }
}

#[test]
fn listed_targets_agree_with_the_analyzer() {
    let targets =
        only_targets(compare_text("AQT-xx\t3\t24.0000%\nAQT-xx\t2\t76.0000%"));

    assert_eq!(targets.len(), 3);
    assert!(targets.iter().all(TargetComparison::agrees));
    assert!(!targets[1].is_inferred);
}

#[test]
fn target_below_the_listed_ones_is_sure() {
    let targets = only_targets(compare_text("KQT-xxx\t2\t54.8447%"));

    assert_eq!(targets[0].suitplay_percent, 100.0);
    assert!(targets[0].is_inferred);
    assert!(targets[0].agrees());
}

#[test]
fn target_above_the_listed_ones_is_impossible() {
    let targets = only_targets(compare_text("KQT-xxx\t2\t54.8447%"));

    assert_eq!(targets[2].suitplay_percent, 0.0);
    assert!(targets[2].is_inferred);
    assert!(targets[2].agrees());
}

#[test]
fn target_zero_means_no_trick_is_possible() {
    let targets = only_targets(compare_text("Q9-63\t0\t0.0000%"));

    assert_eq!(targets.len(), 2);
    assert!(targets.iter().all(|target| target.suitplay_percent == 0.0));
    assert!(targets.iter().all(TargetComparison::agrees));
}

#[test]
fn differing_chance_is_flagged() {
    let targets = only_targets(compare_text("AQ-xx\t2\t55.0000%"));

    assert!(!targets[1].agrees());
    assert!(
        suitplay_report(&compare_text("AQ-xx\t2\t55.0000%"))
            .contains("DIFFERS  AQ-xx@2")
    );
}

#[test]
fn suitplay_error_is_reported() {
    let comparisons = compare_text("x-x\terror\tSuitPlay rejected the holding");

    assert_eq!(
        comparisons[0].outcome,
        Outcome::SuitPlayError("SuitPlay rejected the holding".to_string())
    );
}

#[test]
fn unreadable_holding_is_incomparable() {
    let comparisons = compare_text("AQ-Qx\t2\t50.0000%");

    let Outcome::Incomparable(reason) = &comparisons[0].outcome else {
        panic!("compared: {:?}", comparisons[0].outcome);
    };
    assert!(reason.contains("both hands hold the Q"), "{reason}");
}

#[test]
fn malformed_line_names_its_line() {
    let error = compare_with_suitplay("AQ-xx\t2".as_bytes())
        .expect_err("a line without a chance");

    assert!(error.0.contains("line 1"), "{}", error.0);
}
