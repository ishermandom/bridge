// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Prints each best strategy's chance at every target, then the full line.

use suit_combinations::analysis::{analyze, percent_of_deals};
use suit_combinations::notation::parse_problem;

fn main() {
    for text in std::env::args().skip(1) {
        let problem = parse_problem(&text).expect("problem");
        let analysis = analyze(problem);
        println!("{text}: {} best strategies", analysis.best.len());
        for (index, result) in analysis.best.iter().enumerate() {
            let percents: Vec<String> = result
                .deals_by_target
                .iter()
                .map(|&deals| format!("{:.2}%", percent_of_deals(deals)))
                .collect();
            println!("  strategy {index}: by target {}", percents.join(" / "));
        }
        println!("{}\n", analysis.full_line_words());
    }
}
