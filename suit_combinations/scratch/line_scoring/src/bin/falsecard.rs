// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Checks tasks.md #passed-up-guarantee's hypothesis for AQ942 opposite J73
//! for 4 tricks. After low to the Q with West's 6, East chooses a card. For
//! each card East could play, prints whether any continuation still makes 4
//! tricks in the layout where West held only the 6 and East KT85, and what
//! making them there would cost in the branch's other layouts.

use suit_combinations::cards::{Rank, rank_for_symbol, rank_symbol};
use suit_combinations::layout_set::LayoutSet;
use suit_combinations::layouts::{Defender, Layouts};
use suit_combinations::notation::parse_problem;
use suit_combinations::solver::{
    DefenderPlay, FollowPlay, Hand, Position, Solver, Trick,
};

fn rank(symbol: char) -> Rank {
    rank_for_symbol(symbol).expect("a rank symbol")
}

/// A defender's cards in a layout, with an `x` for each card of a group
/// holding more than one card.
fn holding(layouts: &Layouts, defender: Defender, index: usize) -> String {
    let mut text = String::new();
    for (group_index, group) in layouts.groups.iter().enumerate() {
        let count = layouts.count_of(defender, group_index, index);
        if group.size() == 1 {
            if count == 1 {
                text.push(rank_symbol(group.top()));
            }
        } else {
            text.push_str(&"x".repeat(usize::from(count)));
        }
    }
    if text.is_empty() {
        "-".to_string()
    } else {
        text
    }
}

fn percent(layouts: &Layouts, set: LayoutSet, base: LayoutSet) -> f64 {
    100.0 * layouts.weight(set) as f64 / layouts.weight(base) as f64
}

fn main() {
    let problem = parse_problem("AQ942-J73@4").expect("a valid problem");
    let layouts = Layouts::new(problem.combination);
    let mut solver = Solver::new(&layouts, 4, 5);
    let start = Position::start(&layouts);
    for (index, group) in layouts.groups.iter().enumerate() {
        let ranks: String = group.ranks.descending().map(rank_symbol).collect();
        println!("group {index}: {ranks}");
    }
    let small_group = layouts.groups.len() - 1;
    let small = DefenderPlay::Group(small_group);
    // Low to the Q: South leads the 3, West plays a small card, North the Q.
    let trick = Trick::led(start, Hand::South, rank('3'))
        .with_defender_play(small)
        .with_third(FollowPlay::Card(rank('Q')));
    let kt85 = layouts
        .all
        .indices()
        .find(|&index| {
            layouts.length_of(Defender::West, index) == 1
                && layouts.count_of(Defender::West, small_group, index) == 1
        })
        .expect("the layout West 6, East KT85");
    println!(
        "watched layout: West {} East {}\n",
        holding(&layouts, Defender::West, kt85),
        holding(&layouts, Defender::East, kt85)
    );

    for (play, _) in solver.defender_options(trick) {
        let name = match play {
            DefenderPlay::Group(group) => {
                if group == small_group {
                    "a small card".to_string()
                } else {
                    format!("the {}", rank_symbol(layouts.groups[group].top()))
                }
            }
            DefenderPlay::ShowOut => "shows out".to_string(),
        };
        let next = trick.with_defender_play(play).next_position(&layouts);
        let possible = solver.possible_layouts(next);
        let frontier = solver.solve(next);
        let entries: Vec<Vec<LayoutSet>> =
            frontier.results().map(|entry| entry.to_vec()).collect();
        let by_rank = |entry: &&Vec<LayoutSet>| {
            (layouts.weight(entry[0]), layouts.weight(entry[1]))
        };
        let best = entries.iter().max_by_key(by_rank).expect("an entry");
        let best_with_kt85 = entries
            .iter()
            .filter(|entry| entry[0].contains(kt85))
            .max_by_key(by_rank);
        println!(
            "East plays {name}: {} layouts possible, {} frontier entries",
            possible.len(),
            entries.len()
        );
        println!(
            "  best continuation: 4 tricks {:.2}%, 5 tricks {:.2}% of the \
             branch; makes 4 against KT85: {}",
            percent(&layouts, best[0], possible),
            percent(&layouts, best[1], possible),
            best[0].contains(kt85)
        );
        match best_with_kt85 {
            Some(entry) => println!(
                "  best that makes 4 against KT85: 4 tricks {:.2}%, 5 tricks \
                 {:.2}%",
                percent(&layouts, entry[0], possible),
                percent(&layouts, entry[1], possible)
            ),
            None => println!("  no continuation makes 4 against KT85"),
        }
        for index in possible.indices() {
            let mark = |set: LayoutSet| {
                if set.contains(index) { "yes" } else { "no " }
            };
            let with_kt85 =
                best_with_kt85.map(|entry| mark(entry[0])).unwrap_or("-  ");
            println!(
                "    West {:5} East {:5} weight {:8}  best makes 4: {}  \
                 best-with-KT85 makes 4: {}",
                holding(&layouts, Defender::West, index),
                holding(&layouts, Defender::East, index),
                layouts.weights[index],
                mark(best[0]),
                with_kt85
            );
        }
    }
}
