// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Lines that are complete when followed as written, as
//! `suit_combinations/spec.md` #describing-lines describes: every card
//! second hand might play is answered, by the trick's name or a stated
//! answer, and every condition holds as it reads. Shortened, they leave the
//! usual case as "Otherwise", as #shortening-lines describes.

use suit_combinations::analysis::{TOO_MANY_CASES, analyze, line_errors};
use suit_combinations::notation::parse_problem;

/// The best line in words for `problem`, such as `AQ-xx@2`.
fn line(problem: &str) -> String {
    analyze(parse_problem(problem).expect("a valid problem")).line_words()
}

#[test]
fn line_ignores_low_cards_held_only_where_it_fails() {
    // 4 tricks need East's K to be singleton, so East never has a low card to
    // play where the line can win: the A drops the K, and two finesses
    // against West's J963 follow. When West plays the J or the 9, North wins
    // as cheaply as it can and finesses the 8 again.
    assert_eq!(
        line("QT85-A742@4"),
        "Cash the A, then low to the 8. If West plays the J or the 9, low to \
         the 8. Otherwise, low to the T."
    );
}

#[test]
fn line_answers_a_show_out_with_its_own_card() {
    // When West shows out, the Q still makes 2 tricks, so the line plays it
    // rather than the A, and has nothing left to say.
    assert_eq!(line("AQJ-xx@2"), "Low to the Q");
}

#[test]
fn line_states_an_answer_its_name_doesnt_imply() {
    // "Cash the A" implies the A over West's T; the line wins with the Q
    // instead, a play it needs in order to reach the target.
    assert_eq!(
        line("AQxxx-J9x@2"),
        "Cash the A (if West plays the T, play the Q), then low to the J"
    );
}

#[test]
fn line_names_the_unusual_case_and_leaves_the_usual_as_otherwise() {
    // When West plays the K or the J, North wins as cheaply as it can and
    // must finesse again with the T; "then low to the Q" would be wrong
    // there.
    assert_eq!(
        line("AQT-xx@3"),
        "Low to the T. If West plays the K or the J, low to the T. Otherwise, \
         low to the Q."
    );
}

#[test]
fn line_keeps_the_usual_case_as_otherwise_over_one_that_saves_a_part() {
    // Once the Q holds, cashing the A drops West's doubleton K. Making "run
    // the J" the "Otherwise" would save a part, but finesses again for
    // nothing.
    assert_eq!(
        line("AQxxx-J9xx@5"),
        "Low to the Q.\n\
         - If West plays the K and East plays the T, cash the J, then cash \
         the 9.\n\
         - If West plays the K and East plays a low card, cash the J, then \
         cash the Q.\n\
         - If West plays a low card and East plays the T, run the J.\n  \
         - If West plays the K, cash the 9.\n  \
         - Otherwise, cash the A.\n\
         - Otherwise, cash the A."
    );
}

#[test]
fn line_removes_the_most_parts_when_that_leaves_at_least_two_fewer() {
    // Leaving the usual case as "Otherwise" would split four ways after the
    // 7, two of the ways reading the same.
    assert_eq!(
        line("JT97-K83@3"),
        "Run the 7. If East plays the Q, lead the 8 to the J, then run the T. \
         Otherwise, run the J, then low to the T."
    );
}

#[test]
fn line_says_second_hand_won_only_when_its_card_did() {
    // North plays low under West's A, which can't be beaten, keeping the K.
    assert_eq!(
        line("KT9xxx-xxx@5"),
        "Low to the K. If West wins with the A, cash the K. Otherwise, duck a \
         round."
    );
}

#[test]
fn line_too_long_to_spell_out_says_so_rather_than_leaving_cases_out() {
    assert_eq!(line("AQTxxx-xxx@5"), TOO_MANY_CASES);
}

/// One test per problem, each asserting that a reader following the
/// problem's best lines as written reaches the target wherever their
/// strategies do. The problems are ones whose lines once fell short.
macro_rules! lines_reach_their_targets {
    ($($name:ident: $problem:literal,)*) => {
        $(
            #[test]
            fn $name() {
                let problem = parse_problem($problem).expect("a valid problem");
                assert_eq!(line_errors(problem), Vec::<String>::new());
            }
        )*
    };
}

lines_reach_their_targets! {
    kqjx_opposite_xxx_for_2_reaches_its_target: "KQJx-xxx@2",
    akxxx_opposite_xxx_for_3_reaches_its_target: "AKxxx-xxx@3",
    aqxxx_opposite_j9xx_for_4_reaches_its_target: "AQxxx-J9xx@4",
    a987_opposite_jxxx_for_3_reaches_its_target: "A987-Jxxx@3",
    k9xxxx_opposite_ajtx_for_6_reaches_its_target: "K9xxxx-AJTx@6",
    aq76_opposite_t853_for_2_reaches_its_target: "AQ76-T853@2",
    kt97654_opposite_a32_for_7_reaches_its_target: "KT97654-A32@7",
    aqtxxx_opposite_xxx_for_5_reaches_its_target: "AQTxxx-xxx@5",
}
