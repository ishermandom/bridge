// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The ways the defenders' cards can lie: how declarer's cards split them
//! into groups, and how the layouts' weights add up to every deal.

use suit_combinations::cards::SUIT_SIZE;
use suit_combinations::layout_set::LayoutSet;
use suit_combinations::layouts::{DEAL_COUNT, Defender, Layouts};
use suit_combinations::notation::parse_problem;

fn layouts_for(problem: &str) -> Layouts {
    let problem = parse_problem(problem).expect("a valid problem");
    Layouts::new(problem.combination)
}

#[test]
fn declarer_cards_split_the_missing_cards_into_groups() {
    let layouts = layouts_for("AQT-xx@2");

    let sizes: Vec<u8> =
        layouts.groups.iter().map(|group| group.size()).collect();
    // The K; the J; and the 9 down to the 4.
    assert_eq!(sizes, vec![1, 1, 6]);
    assert_eq!(layouts.west_counts.len(), 2 * 2 * 7);
}

#[test]
fn layout_weights_cover_every_deal() {
    for problem in ["AQT-xx@2", "KJxx-A9xx@3", "A-x@1", "AKQJT98765432--@1"] {
        let layouts = layouts_for(problem);
        assert_eq!(layouts.weight(layouts.all), DEAL_COUNT, "{problem}");
    }
}

#[test]
fn a_single_card_is_equally_likely_with_either_defender() {
    let layouts = layouts_for("AQ-xx@2");
    let king_with_west = layouts.at_least(Defender::West, 0, 1);

    assert_eq!(2 * layouts.weight(king_with_west), DEAL_COUNT);
}

#[test]
fn length_sets_partition_the_layouts() {
    let layouts = layouts_for("KQx-xxx@2");
    let lengths = (0..=SUIT_SIZE)
        .map(|count| layouts.with_length(Defender::East, count))
        .fold(LayoutSet::EMPTY, LayoutSet::union);

    assert_eq!(lengths, layouts.all);
}
