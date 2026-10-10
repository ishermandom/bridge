// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Command-line entry point: analyze each suit combination named on the
//! command line, such as `AQT-xx@2`.

use std::process::ExitCode;

use suit_combinations::analysis::analyze;
use suit_combinations::notation::parse_problem;

fn main() -> ExitCode {
    let problems: Vec<String> = std::env::args().skip(1).collect();
    if problems.is_empty() {
        eprintln!("usage: suit_combinations PROBLEM..., such as AQT-xx@2");
        return ExitCode::from(2);
    }
    for text in problems {
        let problem = match parse_problem(&text) {
            Ok(problem) => problem,
            Err(error) => {
                eprintln!("{error}");
                return ExitCode::FAILURE;
            }
        };
        let analysis = analyze(problem);
        println!("{problem}: {:.2}%", analysis.success_percent());
        println!("{}", analysis.line_words());
        println!();
    }
    ExitCode::SUCCESS
}
