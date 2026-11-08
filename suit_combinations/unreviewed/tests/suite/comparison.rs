// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Comparing the analyzer's answers with the rows of the flashcards'
//! input file: what matches, what is flagged, and which rows are skipped
//! or named in an error.

use suit_combinations::comparison::{RowComparison, compare_rows};

const HEADER: &str =
    "North,South,Tricks target,Success %,Best line,Remarks,Source";

fn compare_text(rows: &str) -> Vec<RowComparison> {
    compare_rows(format!("{HEADER}\n{rows}").as_bytes())
        .expect("comparable rows")
}

#[test]
fn matching_row_compares_the_same() {
    let [comparison] = compare_text(
        "AQ,xx,2,50,Low to the Q,Finesse hoping the K is onside,A book",
    )
    .try_into()
    .expect("one row");

    assert!(comparison.success_matches);
    assert!(comparison.line_matches);
    assert_eq!(comparison.problem, "AQ-xx@2");
}

#[test]
fn success_percent_compares_at_the_row_precision() {
    // The row writes one decimal place, so the analyzer's chance is
    // rounded to one place before the two are compared.
    let [comparison] = compare_text("AQ9,xx,2,63.0,x,y,z")
        .try_into()
        .expect("one row");

    assert!(comparison.success_matches);
    assert!(!comparison.line_matches);
}

#[test]
fn differing_success_percent_is_flagged() {
    let [comparison] = compare_text("AQ,xx,2,55,Low to the Q,x,y")
        .try_into()
        .expect("one row");

    assert!(!comparison.success_matches);
    assert_eq!(comparison.success_percent, "50.00");
}

#[test]
fn comment_rows_are_skipped() {
    let comparisons =
        compare_text("# A heading,,,,,,\nKx,xx,1,50,Low to the K,x,y");

    assert_eq!(comparisons.len(), 1);
}

#[test]
fn row_with_too_many_tricks_names_its_row() {
    let error = compare_rows(format!("{HEADER}\nAQ,xx,3,50,x,y,z").as_bytes())
        .expect_err("an impossible target");

    assert!(error.0.contains("row 2"), "{}", error.0);
}
