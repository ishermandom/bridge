// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Lists every layout with, for each best strategy, whether it succeeds at
//! each target.

use suit_combinations::analysis::{analyze, percent_of_deals};
use suit_combinations::cards::rank_symbol;
use suit_combinations::layouts::{Defender, Layouts};
use suit_combinations::notation::parse_problem;

fn holding(layouts: &Layouts, defender: Defender, index: usize) -> String {
    let mut text = String::new();
    for (group_index, group) in layouts.groups.iter().enumerate() {
        let count = layouts.count_of(defender, group_index, index);
        if group.size() == 1 {
            if count == 1 {
                text.push_str(&rank_symbol(group.top()).to_string());
            }
        } else {
            text.push_str(&"x".repeat(usize::from(count)));
        }
    }
    if text.is_empty() { "-".to_string() } else { text }
}

fn main() {
    let text = std::env::args().nth(1).expect("problem");
    let analysis = analyze(parse_problem(&text).expect("problem"));
    let layouts = &analysis.layouts;
    for (strategy, result) in analysis.best.iter().enumerate() {
        println!("strategy {strategy}");
        for index in layouts.all.indices() {
            let marks: Vec<&str> = result
                .layouts_by_target
                .iter()
                .map(|set| if set.contains(index) { "yes" } else { "no " })
                .collect();
            println!(
                "  West {:6} East {:6} {:6.2}%  {}",
                holding(layouts, Defender::West, index),
                holding(layouts, Defender::East, index),
                percent_of_deals(layouts.weights[index]),
                marks.join(" ")
            );
        }
    }
}
