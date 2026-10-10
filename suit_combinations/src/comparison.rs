// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Comparing the analyzer's answers with the rows of the flashcards' input
//! file, `flashcards/input/suit_combinations.csv`.
//!
//! The file's format is in `anki/spec.md` #suit-combination-input. Only the
//! columns the analyzer answers are read: the holdings and target, and the
//! success %, best line, and remarks.

use std::fmt::Write as _;
use std::io::Read;

use crate::analysis::analyze;
use crate::notation::{Combination, Problem, parse_holding};

/// One row's comparison.
#[derive(Debug, PartialEq)]
pub struct RowComparison {
    /// The row's problem, such as `AQT-xx@2`.
    pub problem: String,
    /// The analyzer's chance of success, to two decimal places.
    pub success_percent: String,
    /// The row's success %, as written.
    pub row_success_percent: String,
    /// Whether the two agree once the analyzer's is rounded the way the row's
    /// is written.
    pub success_matches: bool,
    pub line: String,
    pub row_line: String,
    /// Whether the lines agree word for word, ignoring spacing.
    pub line_matches: bool,
    pub remark: String,
    pub row_remark: String,
}

/// Why the input file couldn't be compared.
#[derive(Debug)]
pub struct ComparisonError(pub String);

/// Compare the analyzer with every row of the input file read from `input`.
pub fn compare_rows(
    input: impl Read,
) -> Result<Vec<RowComparison>, ComparisonError> {
    let mut reader =
        csv::ReaderBuilder::new().flexible(true).from_reader(input);
    let headers = reader
        .headers()
        .map_err(|error| {
            ComparisonError(format!("unreadable header: {error}"))
        })?
        .clone();
    let column = |name: &str| {
        headers
            .iter()
            .position(|header| header == name)
            .ok_or_else(|| {
                ComparisonError(format!("the header has no {name:?} column"))
            })
    };
    let north = column("North")?;
    let south = column("South")?;
    let target = column("Tricks target")?;
    let success = column("Success %")?;
    let line = column("Best line")?;
    let remarks = column("Remarks")?;

    let mut comparisons = Vec::new();
    for (index, record) in reader.records().enumerate() {
        // The header is row 1.
        let row_number = index + 2;
        let record = record.map_err(|error| {
            ComparisonError(format!("row {row_number} is unreadable: {error}"))
        })?;
        let cell = |column: usize| record.get(column).unwrap_or("").trim();
        // A comment row, such as a label for the rows below it, starts with
        // `#` (`anki/spec.md` #suit-combination-input).
        if cell(0).starts_with('#') {
            continue;
        }
        let problem = row_problem(cell(north), cell(south), cell(target))
            .map_err(|message| {
                ComparisonError(format!("row {row_number}: {message}"))
            })?;
        let analysis = analyze(problem);
        let percent = analysis.success_percent();
        let row_percent = cell(success);
        let decimals = row_percent
            .split_once('.')
            .map_or(0, |(_, after)| after.len());
        let line_words = analysis.line_words();
        comparisons.push(RowComparison {
            problem: problem.to_string(),
            success_percent: format!("{percent:.2}"),
            row_success_percent: row_percent.to_string(),
            success_matches: format!("{percent:.decimals$}") == row_percent,
            line_matches: squeeze(&line_words) == squeeze(cell(line)),
            line: line_words,
            row_line: cell(line).to_string(),
            remark: analysis.remark(),
            row_remark: cell(remarks).to_string(),
        });
    }
    Ok(comparisons)
}

/// The problem a row states.
fn row_problem(
    north: &str,
    south: &str,
    target: &str,
) -> Result<Problem, String> {
    let north = parse_holding(north).map_err(|error| error.to_string())?;
    let south = parse_holding(south).map_err(|error| error.to_string())?;
    let combination =
        Combination::new(north, south).map_err(|error| error.to_string())?;
    let target: u8 = target
        .parse()
        .map_err(|_| format!("tricks target {target:?} isn't a number"))?;
    let longest = combination.north.len().max(combination.south.len());
    if target == 0 || target > longest {
        return Err(format!(
            "tricks target {target} is outside 1 to {longest}, the longer \
             hand's length"
        ));
    }
    Ok(Problem {
        combination,
        target,
    })
}

/// `text` with each run of whitespace turned into a single space.
fn squeeze(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// The comparisons as a report for reading, ending with a tally.
pub fn report(comparisons: &[RowComparison]) -> String {
    let mut report = String::new();
    let mark = |matches: bool| if matches { "same" } else { "DIFFERS" };
    for comparison in comparisons {
        let _ = writeln!(report, "{}", comparison.problem);
        let _ = writeln!(
            report,
            "  Success %  [{}] {} (row: {})",
            mark(comparison.success_matches),
            comparison.success_percent,
            comparison.row_success_percent
        );
        let _ = writeln!(
            report,
            "  Best line  [{}] {}",
            mark(comparison.line_matches),
            indent_after_first(&comparison.line)
        );
        if !comparison.line_matches {
            let _ = writeln!(
                report,
                "        row:  {}",
                indent_after_first(&comparison.row_line)
            );
        }
        let _ = writeln!(
            report,
            "  Remark     {}",
            indent_after_first(&comparison.remark)
        );
        let _ = writeln!(
            report,
            "        row:  {}",
            indent_after_first(&comparison.row_remark)
        );
        report.push('\n');
    }
    let count = |test: fn(&RowComparison) -> bool| {
        comparisons
            .iter()
            .filter(|comparison| test(comparison))
            .count()
    };
    let _ = writeln!(
        report,
        "{} rows: success % same in {}, best line same in {}",
        comparisons.len(),
        count(|comparison| comparison.success_matches),
        count(|comparison| comparison.line_matches)
    );
    report
}

/// `text` with every line after its first indented to line up under it.
fn indent_after_first(text: &str) -> String {
    text.replace('\n', "\n              ")
}

#[cfg(test)]
mod tests {
    use super::*;

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
        let error =
            compare_rows(format!("{HEADER}\nAQ,xx,3,50,x,y,z").as_bytes())
                .expect_err("an impossible target");

        assert!(error.0.contains("row 2"), "{}", error.0);
    }
}
