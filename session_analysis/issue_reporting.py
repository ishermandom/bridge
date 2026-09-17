# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Report what a parse could not read, in place of raising.

Every capture parser holds to one discipline: an unreadable cell costs that cell
and not the four hundred rows around it (see travellers.md `#issue-reporting`).
Holding to it takes the same two pieces in every parser, so both live here
rather than four times over.

`Failure` states once how a kind of trouble is reported, and `Read` pairs a
value with whatever went wrong producing it.

`console_line` serves the other end: it is how every command prints one of these
issues for a person to read.
"""

import dataclasses
from collections.abc import Mapping

from session_analysis.enums import IssueSeverity
from session_analysis.models import Issue

# The word a command prints before each issue, mapping issue severity onto
# the common logging severity labels.
#
# There is no default label, so printing an issue of a newly added severity
# raises a `KeyError` rather than printing under a guessed label.
_CONSOLE_LABELS: Mapping[IssueSeverity, str] = {
  IssueSeverity.HIGH: 'error',
  IssueSeverity.MEDIUM: 'warning',
  IssueSeverity.LOW: 'warning',
}


@dataclasses.dataclass(frozen=True)
class Read[T]:
  """What a parser read, paired with what it could not.

  Partial success is an ordinary outcome for a capture parser, so its return
  values need somewhere to put the report: a table where most rows could be
  read, a single field that could not, a placeholder standing in for a value the
  source stated unreadably. In each case `value` is as much as could be
  salvaged, and `issues` says what was lost.
  """

  value: T
  issues: tuple[Issue, ...] = ()


@dataclasses.dataclass(frozen=True)
class Failure:
  """A kind of thing a parser can fail to read.

  A failure's code, the field it belongs to, and its severity are fixed per
  category of failure; only the message varies with the row that provoked it.
  Binding the three together defines each category once, so two sites reporting
  the same failure cannot rank it differently.
  """

  code: str
  severity: IssueSeverity
  location: str

  def issue(self, message: str) -> Issue:
    """This kind of failure, as reported against one board or row."""
    return Issue(
      code=self.code,
      severity=self.severity,
      message=message,
      location=self.location,
    )


def console_line(issue: Issue) -> str:
  """An issue as a command prints it: `[error]` or `[warning]`, code, message.

  The brackets visually distinguish the label even when it is next to a long
  message. Every label is padded to the width of the longest, so the codes start
  in one column down a run of issues, and a reader can scan the labels alone.
  """
  width = max(len(f'[{label}]') for label in _CONSOLE_LABELS.values())
  bracketed_label = f'[{_CONSOLE_LABELS[issue.severity]}]'
  return f'{bracketed_label:<{width}}  {issue.code}: {issue.message}'
