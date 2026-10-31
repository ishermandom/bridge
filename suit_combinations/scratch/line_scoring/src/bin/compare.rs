// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Scores lines whose first tricks are forced, with the solver's best play
//! after that.

use suit_combinations::analysis::percent_of_deals;
use suit_combinations::cards::{Rank, rank_for_symbol};
use suit_combinations::layout_set::LayoutSet;
use suit_combinations::layouts::Layouts;
use suit_combinations::notation::parse_problem;
use suit_combinations::solver::{
    DefenderPlay, FollowPlay, Hand, Position, Solver, Trick,
};

type Outcome = Vec<LayoutSet>;
type Front = Vec<Outcome>;

/// One forced trick: lead `lead` (or the leader's lowest card) from
/// `leader`, and play `target` from the other hand if second hand plays
/// lower than it or shows out.
#[derive(Clone, Copy)]
struct Forced {
    leader: Hand,
    lead: Option<Rank>,
    target: Rank,
}

fn dominates(a: &Outcome, b: &Outcome) -> bool {
    a != b && a.iter().zip(b).all(|(x, y)| x.is_superset(*y))
}

fn prune(front: Front) -> Front {
    let mut kept: Front = Vec::new();
    for outcome in front {
        if kept.iter().any(|k| k == &outcome || dominates(k, &outcome)) {
            continue;
        }
        kept.retain(|k| !dominates(&outcome, k));
        kept.push(outcome);
    }
    kept
}

fn combine(acc: &Front, child: &Front, outside: LayoutSet) -> Front {
    let mut out = Vec::new();
    for a in acc {
        for c in child {
            out.push(
                a.iter()
                    .zip(c)
                    .map(|(a, c)| a.intersection(c.union(outside)))
                    .collect(),
            );
        }
    }
    prune(out)
}

struct Search<'a, 'b> {
    solver: &'b mut Solver<'a>,
    layouts: &'a Layouts,
    plan: Vec<Forced>,
}

impl Search<'_, '_> {
    fn start_of_trick(&mut self, position: Position, depth: usize) -> Front {
        if let Some(&forced) = self.plan.get(depth) {
            let hand = position.hand(forced.leader);
            let partner = position.hand(forced.leader.partner());
            let lead = forced.lead.filter(|&r| hand.contains(r)).or(
                if forced.lead.is_none() { hand.lowest() } else { None },
            );
            if let Some(lead) = lead {
                if partner.contains(forced.target) {
                    return self.forced_trick(position, forced, lead, depth);
                }
            }
        }
        self.solver
            .solve(position)
            .results()
            .map(|r| r.to_vec())
            .collect()
    }

    fn forced_trick(
        &mut self,
        position: Position,
        forced: Forced,
        lead: Rank,
        depth: usize,
    ) -> Front {
        let trick = Trick::led(position, forced.leader, lead);
        let possible = self.solver.possible_layouts(position);
        let mut acc: Front = vec![vec![possible; self.solver.target_count]];
        for (play, play_layouts) in self.solver.defender_options(trick) {
            let child = trick.with_defender_play(play);
            let is_low = match play {
                DefenderPlay::ShowOut => true,
                DefenderPlay::Group(g) => {
                    self.layouts.groups[g].top() < forced.target
                }
            };
            let thirds = if is_low {
                vec![FollowPlay::Card(forced.target)]
            } else {
                self.solver.third_hand_options(child)
            };
            let mut options: Front = Vec::new();
            for third in thirds {
                options.extend(self.fourth_hand(child.with_third(third), depth));
            }
            acc = combine(&acc, &prune(options), possible.difference(play_layouts));
        }
        acc
    }

    fn fourth_hand(&mut self, trick: Trick, depth: usize) -> Front {
        let possible = self.solver.possible_layouts(trick.position);
        let mut acc: Front = vec![vec![possible; self.solver.target_count]];
        for (play, play_layouts) in self.solver.defender_options(trick) {
            let next = trick.with_defender_play(play).next_position(self.layouts);
            let child = self.start_of_trick(next, depth + 1);
            acc = combine(&acc, &child, possible.difference(play_layouts));
        }
        acc
    }
}

fn rank(symbol: char) -> Rank {
    rank_for_symbol(symbol).expect("a rank symbol")
}

fn report(
    label: &str,
    front: &Front,
    layouts: &Layouts,
    base: u64,
) {
    let percent = |set: LayoutSet| {
        100.0 * layouts.weight(set) as f64 / base as f64
    };
    let best = front
        .iter()
        .max_by_key(|r| (layouts.weight(r[0]), layouts.weight(r[1])))
        .expect("a result");
    let most_fives = front
        .iter()
        .max_by_key(|r| (layouts.weight(r[1]), layouts.weight(r[0])))
        .expect("a result");
    println!(
        "{label:42} best for 4: {:6.2}% / {:6.2}%   best for 5: {:6.2}% / {:6.2}%",
        percent(best[0]),
        percent(best[1]),
        percent(most_fives[0]),
        percent(most_fives[1]),
    );
}

fn main() {
    let problem = parse_problem("AQ942-J73@4").expect("problem");
    let layouts = Layouts::new(problem.combination);
    let mut solver = Solver::new(&layouts, 4, 5);
    let start = Position::start(&layouts);
    let all = layouts.weight(layouts.all);
    let low_to = |target: char| Forced {
        leader: Hand::South,
        lead: None,
        target: rank(target),
    };

    println!("From the start (4 tricks / 5 tricks):");
    let lines: Vec<(&str, Vec<Forced>)> = vec![
        ("best line", vec![]),
        ("low to the Q, then best", vec![low_to('Q')]),
        ("low to the Q, then low to the 9", vec![low_to('Q'), low_to('9')]),
        ("low to the 9, then best", vec![low_to('9')]),
        ("low to the 9, then low to the Q", vec![low_to('9'), low_to('Q')]),
    ];
    for (label, plan) in lines {
        let mut search = Search { solver: &mut solver, layouts: &layouts, plan };
        let front = search.start_of_trick(start, 0);
        report(label, &front, &layouts, all);
    }

    // After low to the Q with West's 6 and East's 5: the 6-5 group is last.
    let small = DefenderPlay::Group(layouts.groups.len() - 1);
    let after_first = Trick::led(start, Hand::South, rank('3'))
        .with_defender_play(small)
        .with_third(FollowPlay::Card(rank('Q')))
        .with_defender_play(small)
        .next_position(&layouts);
    let base = layouts.weight(solver.possible_layouts(after_first));
    println!(
        "\nAfter low to the Q, West 6, East 5 ({:.2}% of deals):",
        percent_of_deals(base)
    );
    let continuations: Vec<(&str, Vec<Forced>)> = vec![
        ("best continuation", vec![]),
        (
            "lead the J and play the 9",
            vec![Forced { leader: Hand::South, lead: Some(rank('J')), target: rank('9') }],
        ),
        ("low to the 9", vec![low_to('9')]),
    ];
    for (label, plan) in continuations {
        let mut search = Search { solver: &mut solver, layouts: &layouts, plan };
        let front = search.start_of_trick(after_first, 0);
        report(label, &front, &layouts, base);
    }

    println!("\nEach trick-2 lead from there (4 tricks / 5 tricks):");
    for (leader, lead) in solver.leads(after_first) {
        let front: Front = solver
            .defender_turn(Trick::led(after_first, leader, lead))
            .results()
            .map(|r| r.to_vec())
            .collect();
        report(
            &format!("{leader:?} leads the {}", suit_combinations::cards::rank_symbol(lead)),
            &front,
            &layouts,
            base,
        );
        let trick = Trick::led(after_first, leader, lead);
        for (play, play_layouts) in solver.defender_options(trick) {
            let child = trick.with_defender_play(play);
            let play_base = layouts.weight(play_layouts);
            let name = match play {
                DefenderPlay::Group(g) => format!(
                    "{}",
                    suit_combinations::cards::rank_symbol(layouts.groups[g].top())
                ),
                DefenderPlay::ShowOut => "shows out".to_string(),
            };
            for third in solver.third_hand_options(child) {
                let front: Front = solver
                    .defender_turn(child.with_third(third))
                    .results()
                    .map(|r| r.to_vec())
                    .collect();
                let third_name = match third {
                    FollowPlay::Card(card) => format!("{}", suit_combinations::cards::rank_symbol(card)),
                    FollowPlay::Discard => "discard".to_string(),
                };
                report(
                    &format!("    second hand {name}, third hand {third_name}"),
                    &front,
                    &layouts,
                    play_base,
                );
            }
        }
    }
}
