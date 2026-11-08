// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Sets of layouts, one bit per layout: indexing across words, taking the
//! leading layouts, and combining or comparing two sets.

use suit_combinations::layout_set::LayoutSet;

fn set_of(indices: &[usize]) -> LayoutSet {
    let mut set = LayoutSet::EMPTY;
    for &index in indices {
        set.insert(index);
    }
    set
}

#[test]
fn indices_span_every_word() {
    let set = set_of(&[0, 63, 64, 161]);

    assert_eq!(set.indices().collect::<Vec<_>>(), vec![0, 63, 64, 161]);
    assert_eq!(set.len(), 4);
}

#[test]
fn first_holds_exactly_the_leading_layouts() {
    let set = LayoutSet::first(70);

    assert!(set.contains(69));
    assert!(!set.contains(70));
    assert_eq!(set.len(), 70);
}

#[test]
fn set_operations_combine_elementwise() {
    let left = set_of(&[1, 2, 100]);
    let right = set_of(&[2, 3, 100]);

    assert_eq!(left.union(right), set_of(&[1, 2, 3, 100]));
    assert_eq!(left.intersection(right), set_of(&[2, 100]));
    assert_eq!(left.difference(right), set_of(&[1]));
}

#[test]
fn superset_holds_every_layout_of_the_other() {
    let whole = set_of(&[1, 2, 100]);

    assert!(whole.is_superset(set_of(&[2, 100])));
    assert!(whole.is_superset(LayoutSet::EMPTY));
    assert!(!whole.is_superset(set_of(&[3])));
}
