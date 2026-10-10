// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Command-line entry point: analyze each suit combination named on the
//! command line, such as `AQT-xx@2`, or, given `-`, each line of standard
//! input. `compare FILE` instead compares the analyzer with each row of the
//! flashcards' input file.

use std::io::{BufRead, Write};
use std::process::ExitCode;

use suit_combinations::analysis::analyze;
use suit_combinations::comparison::{compare_rows, report};
use suit_combinations::notation::parse_problem;

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    if arguments.is_empty() {
        eprintln!(
            "usage: suit_combinations PROBLEM..., such as AQT-xx@2, or - to \
             read one problem per line of standard input, or compare FILE"
        );
        return ExitCode::from(2);
    }
    if let [command, path] = arguments.as_slice()
        && command == "compare"
    {
        return compare(path);
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
