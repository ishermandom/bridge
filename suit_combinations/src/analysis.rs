// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The best strategies for a problem, their chances, and their lines.

use crate::describe::{Describer, Line, line_words};
use crate::layout_set::LayoutSet;
use crate::layouts::{DEAL_COUNT, Layouts};
use crate::notation::Problem;
use crate::solver::{Position, Solver};

/// One best strategy: its result and its line of play.
#[derive(Clone, PartialEq, Eq, Debug)]
pub struct BestResult {
    /// For each target from the problem's up to the longer hand's length, the
    /// layouts where the strategy wins at least that many tricks.
    pub layouts_by_target: Vec<LayoutSet>,
    /// For each of those targets, how many deals the strategy reaches it in.
    pub deals_by_target: Vec<u64>,
    /// The line of play.
    pub line: Line,
}

impl BestResult {
    /// The chance, in percent, of reaching the problem's target.
    pub fn success_percent(&self) -> f64 {
        percent_of_deals(self.deals_by_target[0])
    }
}

/// The best strategies for a problem.
#[derive(Debug)]
pub struct Analysis {
    pub problem: Problem,
    pub layouts: Layouts,
    /// The best strategies, which tie with one another.
    ///
    /// A strategy is best when no other reaches the target more often; among
    /// those that tie, the best reach one overtrick most often, then two, and
    /// so on.
    /// Strategies that win in the same layouts count once.
    pub best: Vec<BestResult>,
}

impl Analysis {
    /// The chance, in percent, that a best strategy reaches the target.
    pub fn success_percent(&self) -> f64 {
        self.best[0].success_percent()
    }

    /// The intuition behind the best line, such as "Finesse hoping the K is
    /// onside".
    pub fn remark(&self) -> String {
        crate::remark::remark(&self.layouts, &self.best)
    }

    /// The best line in words, offering each best strategy in turn when
    /// several tie with different lines.
    pub fn line_words(&self) -> String {
        let mut lines: Vec<String> = Vec::new();
        for result in &self.best {
            let words = line_words(&result.line, &self.layouts);
            if !lines.contains(&words) {
                lines.push(words);
            }
        }
        if lines.len() == 1 {
            return lines.remove(0);
        }
        let bullets: Vec<String> =
            lines.iter().map(|line| format!("* {line}")).collect();
        format!("Either:\n{}", bullets.join("\n"))
    }
}

/// `deals` as a percentage of all deals.
pub fn percent_of_deals(deals: u64) -> f64 {
    100.0 * deals as f64 / DEAL_COUNT as f64
}

/// Find the best strategies for `problem`.
pub fn analyze(problem: Problem) -> Analysis {
    let layouts = Layouts::new(problem.combination);
    let longest = problem
        .combination
        .north
        .len()
        .max(problem.combination.south.len());
    let best = {
        let mut solver = Solver::new(&layouts, problem.target, longest);
        let frontier = solver.solve(Position::start(&layouts));
        let candidates: Vec<(Vec<LayoutSet>, Vec<u64>)> = frontier
            .results()
            .map(|result| {
                let deals =
                    result.iter().map(|&set| layouts.weight(set)).collect();
                (result.to_vec(), deals)
            })
            .collect();
        // Comparing the counts target by target, the problem's own first,
        // ranks overtricks below the target and each overtrick below the
        // one before it.
        let top = candidates
            .iter()
            .map(|(_, deals)| deals.clone())
            .max()
            .expect("a frontier always holds a result");
        let mut describer = Describer::new(&mut solver);
        candidates
            .into_iter()
            .filter(|(_, deals)| *deals == top)
            .map(|(layouts_by_target, deals_by_target)| {
                let line = describer.describe(&layouts_by_target);
                BestResult {
                    layouts_by_target,
                    deals_by_target,
                    line,
                }
            })
            .collect()
    };
    Analysis {
        problem,
        layouts,
        best,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::notation::parse_problem;

    fn analyze_text(problem: &str) -> Analysis {
        analyze(parse_problem(problem).expect("a valid problem"))
    }

    #[test]
    fn best_strategy_makes_the_most_overtricks_among_ties() {
        // Finessing the T first or the Q first both make 2 tricks unless East
        // holds the K and J; either way, 3 tricks need both honors with West.
        let analysis = analyze_text("AQT-xx@2");

        let deals = &analysis.best[0].deals_by_target;
        assert_eq!(deals.len(), 2);
        assert!((percent_of_deals(deals[0]) - 76.0).abs() < 1e-9);
        assert!((percent_of_deals(deals[1]) - 24.0).abs() < 1e-9);
    }

    #[test]
    fn mirror_image_lines_tie_as_separate_results() {
        // A two-way finesse: playing West or East for the Q wins equally
        // often, in different layouts.
        let analysis = analyze_text("Axx-KJT@3");

        assert_eq!(analysis.best.len(), 2);
        assert_ne!(
            analysis.best[0].layouts_by_target,
            analysis.best[1].layouts_by_target
        );
    }
}
