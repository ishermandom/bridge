// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Finds the best line of play for a bridge suit combination, and explains it.
//!
//! The design is in `suit_combinations/spec.md`.

pub mod analysis;
pub mod cards;
pub mod comparison;
pub mod describe;
pub mod layout_set;
pub mod layouts;
pub mod notation;
pub mod remark;
pub mod solver;
