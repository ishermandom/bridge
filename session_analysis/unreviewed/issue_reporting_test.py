# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for how a command prints an issue for a person to read.

The module under test, `issue_reporting`, is already reviewed; only these tests
await review, and they move up beside it once reviewed.
"""

import pytest

from session_analysis.enums import IssueSeverity
from session_analysis.issue_reporting import console_line
from session_analysis.models import Issue


def _make_issue(severity: IssueSeverity) -> Issue:
  """An issue whose code and message stay the same across severities."""
  return Issue(
    code='no_capture_of_date_fits',
    severity=severity,
    message='pabc-morn-2026-09-15 has no capture',
    location='session',
  )


# --- printing an issue ---


def test_a_high_severity_issue_prints_as_an_error() -> None:
  line = console_line(_make_issue(IssueSeverity.HIGH))

  # Padded to the width of `[warning]`, so the code starts in the same column as
  # a warning's.
  assert line == (
    '[error]    no_capture_of_date_fits: pabc-morn-2026-09-15 has no capture'
  )


@pytest.mark.parametrize('severity', [IssueSeverity.MEDIUM, IssueSeverity.LOW])
def test_a_lesser_issue_prints_as_a_warning(severity: IssueSeverity) -> None:
  line = console_line(_make_issue(severity))

  assert line == (
    '[warning]  no_capture_of_date_fits: pabc-morn-2026-09-15 has no capture'
  )
