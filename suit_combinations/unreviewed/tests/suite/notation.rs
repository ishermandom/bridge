// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Parsing holdings and problems from their notation, such as `AQT-xx@2`,
//! and rejecting notation that is malformed or names an impossible deal.

use suit_combinations::cards::{RankSet, rank_for_symbol};
use suit_combinations::notation::{parse_holding, parse_problem};

fn ranks(cards: &str) -> RankSet {
    cards.chars().fold(RankSet::EMPTY, |set, symbol| {
        set.with(rank_for_symbol(symbol).expect("a rank symbol"))
    })
}

#[test]
fn holding_reads_named_and_small_cards() {
    let holding = parse_holding("AQ10x").expect("a valid holding");

    assert_eq!(holding.named, ranks("AQT"));
    assert_eq!(holding.small_count, 1);
    assert_eq!(holding.to_string(), "AQTx");
}

#[test]
fn holding_accepts_every_void_spelling() {
    for spelling in ["", "-", "v", "void", "(void)", " "] {
        let holding = parse_holding(spelling).expect("a void");
        assert!(holding.is_empty(), "{spelling:?}");
    }
}

#[test]
fn holding_rejects_cards_out_of_order() {
    assert!(parse_holding("QA").is_err());
    assert!(parse_holding("AA").is_err());
    assert!(parse_holding("AxQ").is_err());
}

#[test]
fn holding_rejects_unknown_cards() {
    let error = parse_holding("AZ").expect_err("an unknown card");
    assert!(error.to_string().contains("'Z'"), "{error}");
}

#[test]
fn small_cards_take_the_lowest_free_ranks() {
    let problem = parse_problem("AQT-xx@2").expect("a valid problem");

    assert_eq!(problem.combination.north, ranks("AQT"));
    assert_eq!(problem.combination.south, ranks("32"));
    assert_eq!(problem.target, 2);
}

#[test]
fn small_cards_skip_named_spots() {
    let problem = parse_problem("A4x-xx@1").expect("a valid problem");

    // North's x must sit below its 4, so North takes the 2.
    assert_eq!(problem.combination.north, ranks("A42"));
    assert_eq!(problem.combination.south, ranks("53"));
}

#[test]
fn problem_names_a_void_after_the_separator() {
    let problem = parse_problem("AKQ--@3").expect("a valid problem");

    assert!(problem.combination.south.is_empty());
    assert_eq!(problem.to_string(), "AKQ-(void)@3");
}

#[test]
fn problem_rejects_a_card_in_both_hands() {
    assert!(parse_problem("AQ-Qx@1").is_err());
}

#[test]
fn problem_rejects_a_target_beyond_the_longer_hand() {
    let error = parse_problem("AQ-xx@3").expect_err("too many tricks");
    assert!(error.to_string().contains("1 to 2"), "{error}");
}
