// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! The best strategies for a problem, their chances, and their lines.

use crate::describe::{Describer, Line, line_words};
use crate::layout_set::LayoutSet;
use crate::layouts::{DEAL_COUNT, Layouts};
use crate::notation::Problem;
use crate::shorten::OtherwiseRule;
use crate::solver::{Position, Solver};

/// The longest line, in characters, that `Analysis::line_words` spells out:
/// about as much as a flashcard's answer can hold. A complete line any
/// longer is replaced by `TOO_MANY_CASES` rather than cut short, since
/// cutting it would leave out cases where the play differs.
pub const MAX_LINE_LENGTH: usize = 400;

/// How many fewer parts, across all of a problem's tied lines, removing the
/// most parts must leave to replace the usual case as "Otherwise": one fewer
/// reads better about as often as it reads worse.
const MIN_PARTS_SAVED: usize = 2;

/// What `Analysis::line_words` says instead of a line too long to spell out,
/// or one that fails its check.
pub const TOO_MANY_CASES: &str =
    "The best play depends on too many cases to describe here";

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
    /// Whether a reader following the line as written reaches the target
    /// wherever the strategy does, as `Describer::check` finds, and why not.
    pub check: Result<(), String>,
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
    /// several tie with different lines, or saying that it has too many
    /// cases to describe when it runs past `MAX_LINE_LENGTH` or a line
    /// fails its check.
    pub fn line_words(&self) -> String {
        let words = self.full_line_words();
        let is_checked = self.best.iter().all(|result| result.check.is_ok());
        if words.chars().count() > MAX_LINE_LENGTH || !is_checked {
            return TOO_MANY_CASES.to_string();
        }
        words
    }

    /// The best line in words, however long, offering each best strategy in
    /// turn when several tie with different lines.
    pub fn full_line_words(&self) -> String {
        if self.best[0].deals_by_target[0] == 0 {
            return "No line can succeed".to_string();
        }
        either_words(self.best.iter().map(|result| &result.line), &self.layouts)
    }
}

/// `lines` in words, offering each in turn when they read differently.
fn either_words<'l>(
    lines: impl IntoIterator<Item = &'l Line>,
    layouts: &Layouts,
) -> String {
    let mut distinct: Vec<String> = Vec::new();
    for line in lines {
        let words = line_words(line, layouts);
        if !distinct.contains(&words) {
            distinct.push(words);
        }
    }
    if distinct.len() == 1 {
        return distinct.remove(0);
    }
    let bullets: Vec<String> =
        distinct.iter().map(|words| format!("* {words}")).collect();
    format!("Either:\n{}", bullets.join("\n"))
}

/// `deals` as a percentage of all deals.
pub fn percent_of_deals(deals: u64) -> f64 {
    100.0 * deals as f64 / DEAL_COUNT as f64
}

/// Why each of `problem`'s best lines, if any, would fail a reader who
/// follows it, as `Describer::check` finds: empty when every line reaches
/// the target wherever its strategy does.
pub fn line_errors(problem: Problem) -> Vec<String> {
    analyze(problem)
        .best
        .into_iter()
        .filter_map(|result| result.check.err())
        .collect()
}

/// Find the best strategies for `problem`, describing and checking each
/// one's line.
pub fn analyze(problem: Problem) -> Analysis {
    let layouts = Layouts::new(problem.combination);
    let longest = problem.combination.longer_hand_length();
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
        let tied: Vec<(Vec<LayoutSet>, Vec<u64>)> = candidates
            .into_iter()
            .filter(|(_, deals)| *deals == top)
            .collect();
        let mut describer = Describer::new(&mut solver);
        let full_lines: Vec<Line> = tied
            .iter()
            .map(|(layouts_by_target, _)| describer.describe(layouts_by_target))
            .collect();
        let mut shorten_all = |rule: OtherwiseRule| -> Vec<Line> {
            full_lines
                .iter()
                .zip(&tied)
                .map(|(line, (layouts_by_target, _))| {
                    describer.shorten(line.clone(), layouts_by_target, rule)
                })
                .collect()
        };
        // The usual case as "Otherwise" reads most like a teacher, so letting
        // the most parts go instead is worth it only when the usual case
        // leaves the answer past the limit, which counts the tied lines
        // together as `Analysis::line_words` shows them, or leaves at least
        // `MIN_PARTS_SAVED` more conditions to read.
        let mut lines = shorten_all(OtherwiseRule::Usual);
        let length = either_words(&lines, &layouts).chars().count();
        let usual_parts: usize = lines.iter().map(Line::part_count).sum();
        if length > MAX_LINE_LENGTH || usual_parts >= MIN_PARTS_SAVED {
            let fewest = shorten_all(OtherwiseRule::FewestParts);
            let fewest_parts: usize = fewest.iter().map(Line::part_count).sum();
            if length > MAX_LINE_LENGTH
                || fewest_parts + MIN_PARTS_SAVED <= usual_parts
            {
                lines = fewest;
            }
        }
        tied.into_iter()
            .zip(lines)
            .map(|((layouts_by_target, deals_by_target), line)| {
                let check = describer.check(&line, &layouts_by_target);
                BestResult {
                    layouts_by_target,
                    deals_by_target,
                    line,
                    check,
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

/// The chance, in percent, that a best strategy reaches `problem`'s target.
///
/// Unlike `analyze`, this tracks no overtricks and describes no line, which
/// makes it the quick way to check many problems' chances.
pub fn best_success_percent(problem: Problem) -> f64 {
    let layouts = Layouts::new(problem.combination);
    let mut solver = Solver::new(&layouts, problem.target, problem.target);
    let frontier = solver.solve(Position::start(&layouts));
    let best_deals = frontier
        .results()
        .map(|result| layouts.weight(result[0]))
        .max()
        .expect("a frontier always holds a result");
    percent_of_deals(best_deals)
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
    fn hopeless_target_says_no_line_succeeds() {
        // Whoever holds the A and K wins both rounds with them.
        let analysis = analyze_text("Q9-63@1");

        assert_eq!(analysis.line_words(), "No line can succeed");
        assert_eq!(
            analysis.remark(),
            "Best defense always holds declarer below the target"
        );
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
