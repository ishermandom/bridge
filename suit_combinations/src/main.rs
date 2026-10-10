// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Command-line entry point: analyze each suit combination named on the
//! command line, such as `AQT-xx@2`.

use std::process::ExitCode;
use std::time::Instant;

use suit_combinations::layouts::{DEAL_COUNT, Layouts};
use suit_combinations::notation::parse_problem;
use suit_combinations::solver::{Position, Solver};

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
        let started = Instant::now();
        let layouts = Layouts::new(problem.combination);
        let longest = problem
            .combination
            .north
            .len()
            .max(problem.combination.south.len());
        let mut solver = Solver::new(&layouts, problem.target, longest);
        let frontier = solver.solve(Position::start(&layouts));
        let best = frontier
            .results()
            .map(|result| layouts.weight(result[0]))
            .max()
            .unwrap_or(0);
        println!(
            "{problem}: {:.2}% ({} results, {} positions, {:.1?})",
            100.0 * best as f64 / DEAL_COUNT as f64,
            frontier.len(),
            solver.positions_solved(),
            started.elapsed()
        );
    }
    ExitCode::SUCCESS
}
