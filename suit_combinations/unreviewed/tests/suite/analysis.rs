// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! How `analysis` picks the best strategy for a problem: how it breaks or
//! keeps a tie, and what it reports for a target that no line reaches.

use suit_combinations::analysis::{Analysis, analyze, percent_of_deals};
use suit_combinations::notation::parse_problem;

fn analyze_text(problem: &str) -> Analysis {
    analyze(parse_problem(problem).expect("a valid problem"))
}

#[test]
fn best_strategy_makes_the_most_overtricks_among_ties() {
    // Finessing the T first or the Q first both make 2 tricks unless East
    // holds the K and J; either way, 3 tricks need both honors with West.
    let analysis = analyze_text("AQT-xx@2");

    let deals = &analysis.best[0].deals_by_target;
    assert_eq!(deals.len(), 2);
    assert!((percent_of_deals(deals[0]) - 76.0).abs() < 1e-9);
    assert!((percent_of_deals(deals[1]) - 24.0).abs() < 1e-9);
}

#[test]
fn hopeless_target_says_no_line_succeeds() {
    // Whoever holds the A and K wins both rounds with them.
    let analysis = analyze_text("Q9-63@1");

    assert_eq!(analysis.line_words(), "No line can succeed");
    assert_eq!(
        analysis.remark(),
        "Best defense always holds declarer below the target"
    );
}

#[test]
fn mirror_image_lines_tie_as_separate_results() {
    // A two-way finesse: playing West or East for the Q wins equally
    // often, in different layouts.
    let analysis = analyze_text("Axx-KJT@3");

    assert_eq!(analysis.best.len(), 2);
    assert_ne!(
        analysis.best[0].layouts_by_target,
        analysis.best[1].layouts_by_target
    );
}
