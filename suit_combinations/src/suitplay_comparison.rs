// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

//! Comparing the analyzer's chances with SuitPlay's, as `suitplay/run.sh`
//! prints them.
//!
//! Each line of SuitPlay's results is tab-separated: a holding such as
//! `AQT-xx`, then either a trick target and SuitPlay's chance of it, such as
//! `2` and `76.0000%`, or `error` and why SuitPlay couldn't analyze the
//! holding.
//!
//! SuitPlay lists only some targets: from the most tricks declarer can ever
//! win down to one more than declarer is sure of, or only the most when even
//! those are sure. So a target below the listed ones is sure, and one above
//! them is impossible. When declarer can never win a trick, SuitPlay lists
//! target 0 at 0%.

use std::fmt::Write as _;
use std::io::{BufRead, BufReader, Read};
use std::num::NonZeroUsize;
use std::sync::atomic::{AtomicUsize, Ordering};

use crate::analysis::best_success_percent;
use crate::comparison::ComparisonError;
use crate::notation::{NotationError, parse_problem};

/// The largest difference, in percentage points, that still counts as
/// agreement. SuitPlay rounds its chances to four decimal places, while a real
/// difference is at least one layout, worth over 0.001% in any holding SuitPlay
/// accepts. The 1e-9 absorbs floating-point error at exactly 0.0001.
const PERCENT_TOLERANCE: f64 = 0.0001 + 1e-9;

/// How the analyzer compares with SuitPlay on one holding.
#[derive(Debug, PartialEq)]
pub struct HoldingComparison {
    /// The holding, such as `AQT-xx`.
    pub holding: String,
    pub outcome: Outcome,
}

/// What comparing one holding found.
#[derive(Debug, PartialEq)]
pub enum Outcome {
    /// Both chances for each target, from 1 trick up to the longer hand's
    /// length.
    Targets(Vec<TargetComparison>),
    /// SuitPlay couldn't analyze the holding, for this reason.
    SuitPlayError(String),
    /// SuitPlay's answer couldn't be compared, for this reason: the analyzer
    /// can't read the holding, or SuitPlay's targets don't follow its pattern.
    Incomparable(String),
}

/// SuitPlay's and the analyzer's chances, in percent, of one target.
#[derive(Debug, PartialEq)]
pub struct TargetComparison {
    pub target: u8,
    pub suitplay_percent: f64,
    /// Whether SuitPlay left the target out, so that its chance follows from
    /// the targets SuitPlay did list.
    pub is_inferred: bool,
    pub analyzer_percent: f64,
}

impl TargetComparison {
    /// Whether the two chances agree, allowing for SuitPlay's rounding.
    pub fn agrees(&self) -> bool {
        (self.suitplay_percent - self.analyzer_percent).abs()
            <= PERCENT_TOLERANCE
    }
}

/// What SuitPlay said about one holding.
enum SuitPlayAnswer {
    /// Its chance, in percent, of each target it listed.
    Chances(Vec<(u8, f64)>),
    /// Why it couldn't analyze the holding.
    Error(String),
}

/// Compare the analyzer with every holding in SuitPlay's results, read from
/// `input`.
///
/// The holdings are shared among threads, each taking the next one not yet
/// taken: a comparison stands alone, and a few hard holdings take seconds.
pub fn compare_with_suitplay(
    input: impl Read,
) -> Result<Vec<HoldingComparison>, ComparisonError> {
    let answers = read_answers(input)?;
    let next_index = AtomicUsize::new(0);
    let thread_count =
        std::thread::available_parallelism().map_or(1, NonZeroUsize::get);
    let mut outcomes: Vec<Option<Outcome>> =
        answers.iter().map(|_| None).collect();
    std::thread::scope(|scope| {
        let workers: Vec<_> = (0..thread_count)
            .map(|_| {
                scope.spawn(|| {
                    let mut finished = Vec::new();
                    loop {
                        let index = next_index.fetch_add(1, Ordering::Relaxed);
                        let Some((holding, answer)) = answers.get(index) else {
                            return finished;
                        };
                        finished
                            .push((index, compare_holding(holding, answer)));
                    }
                })
            })
            .collect();
        for worker in workers {
            let finished = worker.join().expect("a comparison thread panicked");
            for (index, outcome) in finished {
                outcomes[index] = Some(outcome);
            }
        }
    });
    Ok(answers
        .into_iter()
        .zip(outcomes)
        .map(|((holding, _), outcome)| HoldingComparison {
            holding,
            outcome: outcome.expect("a thread compared every holding"),
        })
        .collect())
}

/// What comparing `holding` with SuitPlay's `answer` for it finds.
fn compare_holding(holding: &str, answer: &SuitPlayAnswer) -> Outcome {
    match answer {
        SuitPlayAnswer::Error(reason) => Outcome::SuitPlayError(reason.clone()),
        SuitPlayAnswer::Chances(listed) => {
            match compare_targets(holding, listed) {
                Ok(targets) => Outcome::Targets(targets),
                Err(reason) => Outcome::Incomparable(reason),
            }
        }
    }
}

/// SuitPlay's answer for each holding in `input`, in the order the holdings
/// first appear. This expects a holding's lines to be consecutive, as
/// `suitplay/run.sh` prints them; a holding whose lines aren't gets one
/// answer per run of lines.
fn read_answers(
    input: impl Read,
) -> Result<Vec<(String, SuitPlayAnswer)>, ComparisonError> {
    let mut answers: Vec<(String, SuitPlayAnswer)> = Vec::new();
    for (index, line) in BufReader::new(input).lines().enumerate() {
        let line_number = index + 1;
        let line = line.map_err(|error| {
            ComparisonError(format!(
                "line {line_number} is unreadable: {error}"
            ))
        })?;
        if line.trim().is_empty() {
            continue;
        }
        let malformed = || {
            ComparisonError(format!(
                "line {line_number}, {line:?}, isn't a holding, a target, and \
                 a chance, separated by tabs"
            ))
        };
        let [holding, target, chance] = line
            .split('\t')
            .collect::<Vec<_>>()
            .try_into()
            .map_err(|_| malformed())?;
        // On an error line, the third field is SuitPlay's reason.
        if target == "error" {
            answers.push((
                holding.to_string(),
                SuitPlayAnswer::Error(chance.to_string()),
            ));
            continue;
        }
        let target: u8 = target.parse().map_err(|_| malformed())?;
        let percent: f64 = chance
            .trim_end_matches('%')
            .parse()
            .map_err(|_| malformed())?;
        match answers.last_mut() {
            Some((previous, SuitPlayAnswer::Chances(listed)))
                if previous == holding =>
            {
                listed.push((target, percent));
            }
            _ => answers.push((
                holding.to_string(),
                SuitPlayAnswer::Chances(vec![(target, percent)]),
            )),
        }
    }
    Ok(answers)
}

/// Compare each of `holding`'s targets, given the chances SuitPlay `listed`,
/// or say why they can't be compared.
fn compare_targets(
    holding: &str,
    listed: &[(u8, f64)],
) -> Result<Vec<TargetComparison>, String> {
    let notation_error = |error: NotationError| error.to_string();
    // Any holding has a 1-trick problem, whose combination gives the length.
    let longest = parse_problem(&format!("{holding}@1"))
        .map_err(notation_error)?
        .combination
        .longer_hand_length();
    let listed_targets = listed.iter().map(|&(target, _)| target);
    let (Some(lowest_listed), Some(highest_listed)) =
        (listed_targets.clone().min(), listed_targets.max())
    else {
        unreachable!("a holding's answer starts with one listed target");
    };
    (1..=longest)
        .map(|target| {
            let listed_percent = listed
                .iter()
                .find(|&&(listed_target, _)| listed_target == target)
                .map(|&(_, percent)| percent);
            let (suitplay_percent, is_inferred) = match listed_percent {
                Some(percent) => (percent, false),
                None if target > highest_listed => (0.0, true),
                None if target < lowest_listed => (100.0, true),
                None => {
                    return Err(format!(
                        "SuitPlay skipped target {target}, between targets it \
                         listed"
                    ));
                }
            };
            let problem = parse_problem(&format!("{holding}@{target}"))
                .map_err(notation_error)?;
            Ok(TargetComparison {
                target,
                suitplay_percent,
                is_inferred,
                analyzer_percent: best_success_percent(problem),
            })
        })
        .collect()
}

/// The comparisons as a report for reading: each disagreement and each
/// holding that couldn't be compared, then a tally.
pub fn suitplay_report(comparisons: &[HoldingComparison]) -> String {
    let mut report = String::new();
    let mut target_count = 0;
    let mut disagreement_count = 0;
    let mut uncompared_count = 0;
    for comparison in comparisons {
        match &comparison.outcome {
            Outcome::SuitPlayError(reason) => {
                uncompared_count += 1;
                let _ = writeln!(
                    report,
                    "SuitPlay error  {}: {reason}",
                    comparison.holding
                );
            }
            Outcome::Incomparable(reason) => {
                uncompared_count += 1;
                let _ = writeln!(
                    report,
                    "INCOMPARABLE  {}: {reason}",
                    comparison.holding
                );
            }
            Outcome::Targets(targets) => {
                target_count += targets.len();
                for target in targets.iter().filter(|target| !target.agrees()) {
                    disagreement_count += 1;
                    let inferred = if target.is_inferred {
                        " (inferred)"
                    } else {
                        ""
                    };
                    let _ = writeln!(
                        report,
                        "DIFFERS  {}@{}: SuitPlay {:.4}%{inferred}, analyzer \
                         {:.4}%",
                        comparison.holding,
                        target.target,
                        target.suitplay_percent,
                        target.analyzer_percent
                    );
                }
            }
        }
    }
    let _ = writeln!(
        report,
        "{} holdings, {target_count} targets: {} agree, \
         {disagreement_count} differ; {uncompared_count} holdings couldn't be \
         compared",
        comparisons.len(),
        target_count - disagreement_count
    );
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The comparisons for SuitPlay results given as `text`.
    fn compare_text(text: &str) -> Vec<HoldingComparison> {
        compare_with_suitplay(text.as_bytes()).expect("comparable results")
    }

    /// The single holding's target comparisons in `comparisons`.
    fn only_targets(
        comparisons: Vec<HoldingComparison>,
    ) -> Vec<TargetComparison> {
        let [comparison] = comparisons.try_into().expect("one holding");
        match comparison.outcome {
            Outcome::Targets(targets) => targets,
            other => panic!("not compared: {other:?}"),
        }
    }

    #[test]
    fn listed_targets_agree_with_the_analyzer() {
        let targets = only_targets(compare_text(
            "AQT-xx\t3\t24.0000%\nAQT-xx\t2\t76.0000%",
        ));

        assert_eq!(targets.len(), 3);
        assert!(targets.iter().all(TargetComparison::agrees));
        assert!(!targets[1].is_inferred);
    }

    #[test]
    fn target_below_the_listed_ones_is_sure() {
        let targets = only_targets(compare_text("KQT-xxx\t2\t54.8447%"));

        assert_eq!(targets[0].suitplay_percent, 100.0);
        assert!(targets[0].is_inferred);
        assert!(targets[0].agrees());
    }

    #[test]
    fn target_above_the_listed_ones_is_impossible() {
        let targets = only_targets(compare_text("KQT-xxx\t2\t54.8447%"));

        assert_eq!(targets[2].suitplay_percent, 0.0);
        assert!(targets[2].is_inferred);
        assert!(targets[2].agrees());
    }

    #[test]
    fn target_zero_means_no_trick_is_possible() {
        let targets = only_targets(compare_text("Q9-63\t0\t0.0000%"));

        assert_eq!(targets.len(), 2);
        assert!(targets.iter().all(|target| target.suitplay_percent == 0.0));
        assert!(targets.iter().all(TargetComparison::agrees));
    }

    #[test]
    fn differing_chance_is_flagged() {
        let targets = only_targets(compare_text("AQ-xx\t2\t55.0000%"));

        assert!(!targets[1].agrees());
        assert!(
            suitplay_report(&compare_text("AQ-xx\t2\t55.0000%"))
                .contains("DIFFERS  AQ-xx@2")
        );
    }

    #[test]
    fn suitplay_error_is_reported() {
        let comparisons =
            compare_text("x-x\terror\tSuitPlay rejected the holding");

        assert_eq!(
            comparisons[0].outcome,
            Outcome::SuitPlayError("SuitPlay rejected the holding".to_string())
        );
    }

    #[test]
    fn unreadable_holding_is_incomparable() {
        let comparisons = compare_text("AQ-Qx\t2\t50.0000%");

        let Outcome::Incomparable(reason) = &comparisons[0].outcome else {
            panic!("compared: {:?}", comparisons[0].outcome);
        };
        assert!(reason.contains("both hands hold the Q"), "{reason}");
    }

    #[test]
    fn malformed_line_names_its_line() {
        let error = compare_with_suitplay("AQ-xx\t2".as_bytes())
            .expect_err("a line without a chance");

        assert!(error.0.contains("line 1"), "{}", error.0);
    }
}
