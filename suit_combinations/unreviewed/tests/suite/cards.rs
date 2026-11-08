// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Ranks within one suit, and sets of them: reading rank symbols, and
//! finding the ranks above, between, or at either end of a set.

use suit_combinations::cards::{ACE, RankSet, rank_for_symbol, rank_symbol};

#[test]
fn symbols_round_trip_through_ranks() {
    assert_eq!(rank_symbol(ACE), 'A');
    assert_eq!(rank_symbol(0), '2');
    assert_eq!(rank_for_symbol('T'), Some(8));
    assert_eq!(rank_for_symbol('x'), None);
}

#[test]
fn strictly_between_excludes_both_ends() {
    let between = RankSet::strictly_between(ACE, 8);
    assert_eq!(between.descending().collect::<Vec<_>>(), vec![11, 10, 9]);
}

#[test]
fn strictly_between_adjacent_ranks_is_empty() {
    assert!(RankSet::strictly_between(10, 9).is_empty());
    assert!(RankSet::strictly_between(9, 9).is_empty());
}

#[test]
fn above_excludes_the_rank_itself() {
    let above = RankSet::above(10);
    assert_eq!(above.descending().collect::<Vec<_>>(), vec![12, 11]);
    assert!(RankSet::above(ACE).is_empty());
}

#[test]
fn highest_and_lowest_find_the_ends() {
    let set = RankSet::single(3).with(9).with(5);
    assert_eq!(set.highest(), Some(9));
    assert_eq!(set.lowest(), Some(3));
    assert_eq!(RankSet::EMPTY.highest(), None);
}
