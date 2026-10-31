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
use suit_combinations::notation::{Problem, parse_problem};
use suit_combinations::suitplay_comparison::{
    compare_with_suitplay, suitplay_report,
};

/// How to run the program, printed when it's given no arguments.
const USAGE: &str = "\
usage:
  suit_combinations PROBLEM...
      Analyze each problem, such as AQT-xx@2.
  suit_combinations -
      Analyze one problem per line of standard input.
  suit_combinations check PROBLEM...  (or check -)
      Report each problem whose line falls short when followed as written.
  suit_combinations compare FILE
      Compare the analyzer with each row of the flashcards' input file.
  suit_combinations compare-suitplay FILE
      Compare the analyzer with SuitPlay's results from suitplay/run.sh.";

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [] => {
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
        [command, path] if command == "compare" => compare(path),
        [command, path] if command == "compare-suitplay" => {
            compare_suitplay(path)
        }
        [command, rest @ ..] if command == "check" => check(rest),
        problems => analyze_problems(problems),
    }
}

/// Print each problem's success %, best line, and remark; `-` reads one
/// problem per line of standard input.
fn analyze_problems(arguments: &[String]) -> ExitCode {
    let problems = match read_problems(arguments) {
        Ok(problems) => problems,
        Err(exit_code) => return exit_code,
    };
    let mut output = std::io::stdout().lock();
    for problem in problems {
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
    let problems = match read_problems(arguments) {
        Ok(problems) => problems,
        Err(exit_code) => return exit_code,
    };
    let mut failed = 0;
    for &problem in &problems {
        let errors = line_errors(problem);
        if !errors.is_empty() {
            failed += 1;
            println!("{problem}: {}", errors.join("; "));
        }
    }
    println!(
        "{failed} of {} problems have a line that falls short",
        problems.len()
    );
    if failed == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

/// The problems named in `arguments`, or on each line of standard input
/// when `arguments` is just `-`, skipping blank lines. On a problem that
/// can't be read, reports why and returns the exit code to stop with.
fn read_problems(arguments: &[String]) -> Result<Vec<Problem>, ExitCode> {
    let texts: Vec<String> = if arguments == ["-"] {
        match std::io::stdin().lock().lines().collect() {
            Ok(lines) => lines,
            Err(error) => {
                eprintln!("couldn't read standard input: {error}");
                return Err(ExitCode::FAILURE);
            }
        }
    } else {
        arguments.to_vec()
    };
    texts
        .iter()
        .map(|text| text.trim())
        .filter(|text| !text.is_empty())
        .map(|text| {
            parse_problem(text).map_err(|error| {
                eprintln!("{error}");
                ExitCode::FAILURE
            })
        })
        .collect()
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
