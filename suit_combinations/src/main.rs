// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Command-line entry point. With no subcommand, analyze each problem named
//! on the command line, such as `AQT-xx@2`, or, given `-`, each line of
//! standard input. The subcommands:
//!
//! - `check PROBLEM...` or `check -`: report each problem whose line falls
//!   short when followed as written.
//! - `compare FILE`: compare the analyzer with each row of a file in the
//!   flashcards' input format.
//! - `compare-suitplay FILE`: compare the analyzer with SuitPlay's results,
//!   as `suitplay/run.sh` prints them.

use std::io::{BufRead, Write};
use std::process::ExitCode;

use suit_combinations::analysis::{analyze, line_errors};
use suit_combinations::comparison::{compare_rows, report};
use suit_combinations::notation::parse_problem;
use suit_combinations::suitplay_comparison::{
    compare_with_suitplay, suitplay_report,
};

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments.is_empty() {
        eprintln!(
            "usage: suit_combinations PROBLEM..., such as AQT-xx@2, or - to \
             read one problem per line of standard input, or compare FILE, or \
             compare-suitplay FILE, or check PROBLEM... or check -"
        );
        return ExitCode::from(2);
    }
    if let [command, path] = arguments.as_slice() {
        if command == "compare" {
            return compare(path);
        }
        if command == "compare-suitplay" {
            return compare_suitplay(path);
        }
    }
    if arguments.first().is_some_and(|command| command == "check") {
        return check(&arguments[1..]);
    }
    let problems: Vec<String> = if arguments == ["-"] {
        match std::io::stdin().lock().lines().collect() {
            Ok(lines) => lines,
            Err(error) => {
                eprintln!("couldn't read standard input: {error}");
                return ExitCode::FAILURE;
            }
        }
    } else {
        arguments
    };

    let mut output = std::io::stdout().lock();
    for text in problems.iter().filter(|text| !text.trim().is_empty()) {
        let problem = match parse_problem(text.trim()) {
            Ok(problem) => problem,
            Err(error) => {
                eprintln!("{error}");
                return ExitCode::FAILURE;
            }
        };
        let analysis = analyze(problem);
        let written = writeln!(
            output,
            "{problem}: {:.2}%\n{}\n{}\n",
            analysis.success_percent(),
            analysis.line_words(),
            analysis.remark()
        );
        if let Err(error) = written {
            eprintln!("couldn't write the analysis: {error}");
            return ExitCode::FAILURE;
        }
    }
    ExitCode::SUCCESS
}

/// Check that each problem's best lines reach the target when followed as
/// written, printing each problem whose line doesn't and why; `-` reads one
/// problem per line of standard input.
fn check(arguments: &[String]) -> ExitCode {
    let problems: Vec<String> = if arguments == ["-"] {
        match std::io::stdin().lock().lines().collect() {
            Ok(lines) => lines,
            Err(error) => {
                eprintln!("couldn't read standard input: {error}");
                return ExitCode::FAILURE;
            }
        }
    } else {
        arguments.to_vec()
    };
    let mut failed = 0;
    let mut checked = 0;
    for text in problems.iter().filter(|text| !text.trim().is_empty()) {
        let problem = match parse_problem(text.trim()) {
            Ok(problem) => problem,
            Err(error) => {
                eprintln!("{error}");
                return ExitCode::FAILURE;
            }
        };
        checked += 1;
        let errors = line_errors(problem);
        if !errors.is_empty() {
            failed += 1;
            println!("{problem}: {}", errors.join("; "));
        }
    }
    println!("{failed} of {checked} problems have a line that falls short");
    if failed == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

/// Print how the analyzer compares with each row of the input file at
/// `path`.
fn compare(path: &str) -> ExitCode {
    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) => {
            eprintln!("couldn't open {path}: {error}");
            return ExitCode::FAILURE;
        }
    };
    match compare_rows(file) {
        Ok(comparisons) => {
            print!("{}", report(&comparisons));
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{path}: {}", error.0);
            ExitCode::FAILURE
        }
    }
}

/// Print how the analyzer compares with SuitPlay's results in the file at
/// `path`.
fn compare_suitplay(path: &str) -> ExitCode {
    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) => {
            eprintln!("couldn't open {path}: {error}");
            return ExitCode::FAILURE;
        }
    };
    match compare_with_suitplay(file) {
        Ok(comparisons) => {
            print!("{}", suitplay_report(&comparisons));
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{path}: {}", error.0);
            ExitCode::FAILURE
        }
    }
}
