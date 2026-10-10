// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Sets of layouts of the defenders' cards, one bit per layout.

/// The most layouts any combination has.
///
/// Declarer's cards split the defenders' cards into groups; a layout says how
/// many of each group West holds (see `layouts.rs`). The most layouts arise
/// when four declarer cards split nine defender cards into groups of 2, 2, 2,
/// 2, and 1. West can hold 0, 1, or 2 of each pair and 0 or 1 of the single
/// card, so 3 × 3 × 3 × 3 × 2 = 162.
pub const MAX_LAYOUTS: usize = 162;

/// The number of 64-bit words holding a set.
const WORD_COUNT: usize = MAX_LAYOUTS.div_ceil(64);

/// A set of layouts, by index.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default, Debug)]
pub struct LayoutSet([u64; WORD_COUNT]);

impl LayoutSet {
    /// The set holding no layouts.
    pub const EMPTY: LayoutSet = LayoutSet([0; WORD_COUNT]);

    /// The set holding layouts `0..count`.
    pub fn first(count: usize) -> LayoutSet {
        assert!(count <= MAX_LAYOUTS, "{count} layouts exceeds the maximum");
        let mut set = LayoutSet::EMPTY;
        for index in 0..count {
            set.insert(index);
        }
        set
    }

    /// Add the layout at `index`.
    pub fn insert(&mut self, index: usize) {
        self.0[index / 64] |= 1 << (index % 64);
    }

    /// Whether the set holds the layout at `index`.
    pub fn contains(self, index: usize) -> bool {
        self.0[index / 64] & (1 << (index % 64)) != 0
    }

    /// The layouts in either set.
    pub fn union(self, other: LayoutSet) -> LayoutSet {
        LayoutSet(std::array::from_fn(|word| self.0[word] | other.0[word]))
    }

    /// The layouts in both sets.
    pub fn intersection(self, other: LayoutSet) -> LayoutSet {
        LayoutSet(std::array::from_fn(|word| self.0[word] & other.0[word]))
    }

    /// The layouts in this set but not in `other`.
    pub fn difference(self, other: LayoutSet) -> LayoutSet {
        LayoutSet(std::array::from_fn(|word| self.0[word] & !other.0[word]))
    }

    /// Whether every layout in `other` is also in this set.
    pub fn is_superset(self, other: LayoutSet) -> bool {
        (0..WORD_COUNT).all(|word| other.0[word] & !self.0[word] == 0)
    }

    /// Whether the set holds no layouts.
    pub fn is_empty(self) -> bool {
        self.0.iter().all(|&word| word == 0)
    }

    /// The set's words folded together with `|`. A superset's fold
    /// always contains a subset's, so comparing folds, a single word each,
    /// rules out most non-supersets cheaply.
    pub fn folded(self) -> u64 {
        self.0.iter().fold(0, |folded, &word| folded | word)
    }

    /// How many layouts the set holds.
    pub fn len(self) -> usize {
        self.0.iter().map(|word| word.count_ones() as usize).sum()
    }

    /// The indices of the set's layouts, in increasing order.
    pub fn indices(self) -> impl Iterator<Item = usize> {
        (0..WORD_COUNT).flat_map(move |word| {
            let mut bits = self.0[word];
            std::iter::from_fn(move || {
                if bits == 0 {
                    return None;
                }
                let bit = bits.trailing_zeros() as usize;
                // Clear the lowest set bit.
                bits &= bits - 1;
                Some(word * 64 + bit)
            })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
