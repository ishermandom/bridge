// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Every test of the crate, built as one test binary.
//!
//! Cargo builds each file directly under `tests/` as a binary of its own, and
//! every one of them relinks whenever the library changes. One binary links
//! once and runs all the tests in parallel, which matters because
//! `run_tests.sh` runs them at the end of every turn. So a new test file goes
//! in this directory, with a `mod` line below.

mod analysis;
mod brute_force;
mod cards;
mod ccanalyser_checks;
mod comparison;
mod layout_set;
mod layouts;
mod lines;
mod notation;
mod published_examples;
mod remarks;
mod solver;
mod spreadsheet_rows;
mod suitplay_checks;
mod suitplay_comparison;
