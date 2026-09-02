# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Join a digitized sheet to the travellers that record the same session.

The sheet is our own account of the boards we played; a traveller is the
official account of every table's play of every board. Joining them enriches the
sheet with what it never recorded — the deal, the matchpoints, and who we and
our opponents were — and turns every field both records into a cross-check.
travellers.md `#reconciliation` carries the design.

A traveller arrives after the session and sometimes days later, so the join runs
over every pending session on every ingest pass rather than once, when a session
is digitized (`unreviewed.ingest.reconcile_pending_sessions`). Being re-runnable
is what makes that work: a run rewrites every field and finding it owns rather
than adding to what is already there, so a second traveller landing later is
handled by running the whole join again over both — over the session the last
run produced as readily as over the sheet that run started from.

Three properties shape the code:

- **Best-effort throughout.** Every cross-check degrades to skipped rather than
  failing, and a session with no travellers at all passes through unenriched
  rather than raising. What could not be checked is reported as an `Issue`, in
  the same discipline the capture parsers hold to.
- **Neither record is authoritative.** A traveller is machine-generated but not
  therefore right — the declarer especially is a field travellers get wrong
  where our own notes are right. So a disagreement is surfaced for a person to
  settle, and never resolved by preferring one side.
- **Nothing is auto-corrected.** Swap detection suggests; it does not reorder
  the sheet. Two boards with identical results are indistinguishable, so the
  last word belongs to a person looking at the scan.

Which travellers cover a session is settled before this runs: matching a capture
to its session reads the event and date out of the capture, and belongs to
acquisition rather than here.
"""

import dataclasses
import itertools
from collections.abc import Callable, Iterable, Mapping, Sequence

from session_analysis import issue_reporting
from session_analysis.enums import (
  Direction,
  IssueSeverity,
  Penalty,
  Side,
  Strain,
)
from session_analysis.models import (
  Board,
  Contract,
  Deal,
  Issue,
  PairIdentity,
  PlayedContract,
  Resolution,
  Session,
)
from session_analysis.travellers import (
  Traveller,
  TravellerBoard,
  TravellerResult,
  TravellerSource,
)
from session_analysis.unreviewed import deal_checks

# Our own row is what the whole join hangs on, so failing to place it costs the
# board its entire enrichment — the deal included.
_OUR_ROW_NOT_FOUND = issue_reporting.Failure(
  'our_row_not_found', IssueSeverity.HIGH, 'traveller'
)
_OUR_ROW_AMBIGUOUS = issue_reporting.Failure(
  'our_row_ambiguous', IssueSeverity.HIGH, 'traveller'
)

# A traveller that never names us is the wrong session's, which puts everything
# it would have contributed in doubt rather than any one board.
_TRAVELLER_NEVER_NAMES_US = issue_reporting.Failure(
  'traveller_never_names_us', IssueSeverity.HIGH, 'source'
)

# A board the sheet records and no traveller covers. Expected and harmless where
# a hand record lists boards nobody reached; worth saying either way, because
# the board simply goes unenriched.
_BOARD_NOT_IN_TRAVELLERS = issue_reporting.Failure(
  'board_not_in_travellers', IssueSeverity.LOW, 'traveller'
)

# Two sources covering one session state a field differently. Ranked as part of
# the record of play rather than a structural loss, per travellers.md
# `#issue-reporting`.
_SOURCES_DISAGREE = issue_reporting.Failure(
  'traveller_sources_disagree', IssueSeverity.MEDIUM, 'traveller'
)

# The sheet and the traveller disagree. Each field gets its own code so a
# reviewer can tell a misread contract from a misread trick count without
# reading the message.
_CONTRACT_DISAGREEMENT = issue_reporting.Failure(
  'sheet_contract_disagreement', IssueSeverity.MEDIUM, 'outcome'
)
_DECLARER_DISAGREEMENT = issue_reporting.Failure(
  'sheet_declarer_disagreement', IssueSeverity.MEDIUM, 'outcome'
)
_RESULT_DISAGREEMENT = issue_reporting.Failure(
  'sheet_result_disagreement', IssueSeverity.MEDIUM, 'outcome'
)
_PLAY_DISAGREEMENT = issue_reporting.Failure(
  'sheet_play_disagreement', IssueSeverity.MEDIUM, 'outcome'
)

# A suggested row swap. Medium rather than high: the evidence is real but the
# fix is a person's to apply, and a board pair with identical play produces no
# suggestion at all.
_LIKELY_ROW_SWAP = issue_reporting.Failure(
  'likely_row_swap', IssueSeverity.MEDIUM, 'number'
)


# --- our row ---


def _normalized(name: str) -> str:
  """A name reduced to what two spellings of it should share."""
  return ' '.join(name.split()).casefold()


def _name_forms(configured_name: str) -> frozenset[str]:
  """The spellings of the configured name a capture may print.

  Sources differ in how much of a name they give. Both ACBL surfaces print full
  names, and so does a club recap whose standings could be read; a club recap
  whose standings could not be read leaves the surnames its board rows print
  standing instead (tasks.md `#one-winner-recap`).

  Both forms match and nothing else does. Matching a bare surname against every
  printed full name would claim every namesake in the field, which on a club
  game is a real risk rather than a theoretical one.
  """
  full_name = _normalized(configured_name)
  # The last whitespace-separated token, so a middle name or a two-word given
  # name does not shift which part is taken as the surname.
  surname = full_name.rsplit(' ', 1)[-1]
  return frozenset({full_name, surname})


def _names_us(pair: PairIdentity, name_forms: frozenset[str]) -> bool:
  """Whether a pair includes the configured player."""
  return any(_normalized(name) in name_forms for name in pair.names)


@dataclasses.dataclass(frozen=True)
class _OurRow:
  """The traveller row our pair played, and which side of it we sat.

  The side is not a property of the session: a one-winner movement sits one pair
  in both directions over an evening, so it is read per board.
  """

  side: Side
  result: TravellerResult

  @property
  def our_pair(self) -> PairIdentity:
    """Us, as this traveller names us."""
    if self.side is Side.NORTH_SOUTH:
      return self.result.north_south
    return self.result.east_west

  @property
  def opponents(self) -> PairIdentity:
    """The other pair at our table."""
    if self.side is Side.NORTH_SOUTH:
      return self.result.east_west
    return self.result.north_south

  @property
  def matchpoints(self) -> float | None:
    """Our side's matchpoints, or None where the source printed none."""
    if self.side is Side.NORTH_SOUTH:
      return self.result.north_south_matchpoints
    return self.result.east_west_matchpoints


@dataclasses.dataclass(frozen=True)
class _RowMatch:
  """What looking for our row on one traveller board turned up."""

  # Whether any row named us at all, which stays true where several did. A board
  # that named us twice yields no row and is still not a board that failed to
  # name us, and the two want different words from everything downstream.
  names_us: bool
  # Filled only where exactly one row named us; nothing else is taken as ours.
  row: _OurRow | None = None


def _find_our_row(
  board: TravellerBoard, name_forms: frozenset[str]
) -> issue_reporting.Read[_RowMatch]:
  """Find the row our pair played on one traveller board.

  Matching is on our own name alone, in either direction and with any partner:
  the sheet never records who we are, partners vary week to week, and we already
  know who we are — so the join recovers the opponents' identity rather than
  ours (travellers.md `#reconciliation`).

  A board naming us in more than one row — which a name shared with another
  player in the field would produce — yields no row and an issue. A board naming
  us in none yields no row and no issue here: whether that is worth remarking on
  turns on what the rest of the traveller says, which `_merge_board` and
  `build_enrichments` are the ones holding. Neither case is guessed at, because
  every field the board contributes downstream would inherit the guess.
  """
  matches = [
    _OurRow(side=side, result=result)
    for result in board.results
    for side, pair in (
      (Side.NORTH_SOUTH, result.north_south),
      (Side.EAST_WEST, result.east_west),
    )
    if _names_us(pair, name_forms)
  ]

  if not matches:
    return issue_reporting.Read(_RowMatch(names_us=False))

  if len(matches) > 1:
    seated = ', '.join(
      f'{match.our_pair.number}{match.our_pair.side}' for match in matches
    )
    return issue_reporting.Read(
      _RowMatch(names_us=True),
      (
        _OUR_ROW_AMBIGUOUS.issue(
          f'board {board.number} names us in {len(matches)} rows ({seated}), '
          f'so none of them can be taken as ours'
        ),
      ),
    )

  return issue_reporting.Read(_RowMatch(names_us=True, row=matches[0]))


# --- merging the sources ---


@dataclasses.dataclass(frozen=True)
class _Capture:
  """The capture one candidate value for a merged field came from.

  Identified by its path as well as its source, because one source can cover a
  session twice: the club publishes hand-record and result-bearing PBNs alike,
  and both parse as `CLUB_PBN`. Keying a merge on the source alone would let the
  second capture displace the first without a word.
  """

  source: TravellerSource
  path: str

  def __str__(self) -> str:
    """The capture, as a disagreement message names it."""
    return f'{self.source} ({self.path})'


@dataclasses.dataclass(frozen=True)
class BoardEnrichment:
  """What the travellers contribute to one board of the sheet.

  The merged view of every source that covered the board: the deal they agree
  on, the row we played, and what that row says. A field is None where no source
  stated it and where the sources that did contradicted each other — the two are
  told apart by `issues`, which carries a report for the second and nothing for
  the first.
  """

  deal: Deal | None = None
  our_pair: PairIdentity | None = None
  opponents: PairIdentity | None = None
  matchpoints: float | None = None
  # What the travellers say we played, for cross-checking against the sheet.
  resolution: Resolution | None = None
  issues: tuple[Issue, ...] = ()


def _agreed[T](
  candidates: Mapping[_Capture, T],
  *,
  field: str,
  board_number: int,
  describe: Callable[[T], str],
) -> issue_reporting.Read[T | None]:
  """The one value every source that stated a field agreed on.

  A field no source stated yields None and no issue: silence is not a
  disagreement, and a hand record that lists a board nobody played is silent
  about every field but the deal.

  Sources that contradict each other yield None and an issue naming what each
  said. Nothing picks a winner — a silent tiebreak between two records neither
  of which is authoritative is exactly what this phase exists to avoid — so the
  field goes unfilled and a person settles it.
  """
  distinct: list[T] = []
  for value in candidates.values():
    # Compared by equality rather than hashed into a set: a `Deal` holds a
    # mapping of hands, which makes it unhashable while leaving it comparable.
    if value not in distinct:
      distinct.append(value)

  if not distinct:
    return issue_reporting.Read(None)

  if len(distinct) == 1:
    return issue_reporting.Read(distinct[0])

  accounts = '; '.join(
    f'{capture} says {describe(value)}' for capture, value in candidates.items()
  )
  return issue_reporting.Read(
    None,
    (
      _SOURCES_DISAGREE.issue(
        f'board {board_number} {field}: {accounts}. Left unfilled rather than '
        f'settled by preferring a source'
      ),
    ),
  )


def _abbreviates(sparse: str, full: str) -> bool:
  """Whether one spelling of a name is the other's surname.

  Directional: `Last` abbreviates `First Last`, and two spellings that normalize
  alike abbreviate each other.
  """
  sparse, full = _normalized(sparse), _normalized(full)
  return sparse == full or full.rsplit(' ', 1)[-1] == sparse


def _names_one_pair(first: PairIdentity, second: PairIdentity) -> bool:
  """Whether two sources are naming one pair, at whatever detail each gives.

  The seat — number, side, and section — must match outright; nothing about it
  is a matter of detail. The players need only be compatible: a source that
  printed no names at all said nothing to contradict, and a surname stands
  against the full name it abbreviates. Partner order is not assumed to agree
  between two sources, so both orders count as a match.
  """
  if (first.number, first.side, first.section) != (
    second.number,
    second.side,
    second.section,
  ):
    return False

  if not first.names or not second.names:
    return True

  if len(first.names) != len(second.names):
    return False

  def aligns(ordered: tuple[str, ...]) -> bool:
    """Whether the two name lists abbreviate each other in this order."""
    return all(
      _abbreviates(one, other) or _abbreviates(other, one)
      for one, other in zip(first.names, ordered, strict=True)
    )

  return aligns(second.names) or aligns(tuple(reversed(second.names)))


def _fuller(first: PairIdentity, second: PairIdentity) -> PairIdentity:
  """Whichever of two spellings of one pair says more about the players.

  Weighed across the pair rather than name by name, which is right where one
  source is fuller throughout — the shape every capture on hand takes, since a
  recap either recovered its standings or did not.
  """
  # TODO: take the fuller spelling of each name rather than of the pair, so that
  # two sources each fuller in a different name keep both.
  # `Last & Second Person` against `First Last & Person` currently drops one
  # given name whichever way it goes, which is the one case where this does
  # discard something. No capture on hand splits that way, so it waits for one
  # that does.
  written = sum(len(name.split()) for name in first.names)
  against = sum(len(name.split()) for name in second.names)
  return first if written >= against else second


def _agreed_pair(
  candidates: Mapping[_Capture, PairIdentity],
  *,
  field: str,
  board_number: int,
) -> issue_reporting.Read[PairIdentity | None]:
  """The pair every source that named one agreed on, at the fullest detail.

  Sources name one pair at different levels of detail: both ACBL surfaces print
  full names, a club PBN prints surnames or nothing at all, and a club recap
  whose standings could not be read prints the surnames its board rows carry
  (tasks.md `#one-winner-recap`). `Last & Person` and `First Last & Second
  Person` are one pair written twice, not two sources contradicting each other.

  Taking the fuller spelling is not the silent tiebreak this phase exists to
  avoid: nothing is dropped, because the sparser spelling is contained in the
  fuller one. A real contradiction — a different pair number, a different
  section, or names that are not each other's abbreviations — still yields no
  value and an issue, exactly as `_agreed` would give.
  """
  chosen: PairIdentity | None = None
  for pair in candidates.values():
    if not chosen:
      chosen = pair
      continue

    if not _names_one_pair(chosen, pair):
      accounts = '; '.join(
        f'{capture} says {_describe_pair(value)}'
        for capture, value in candidates.items()
      )
      return issue_reporting.Read(
        None,
        (
          _SOURCES_DISAGREE.issue(
            f'board {board_number} {field}: {accounts}. Left unfilled rather '
            f'than settled by preferring a source'
          ),
        ),
      )

    chosen = _fuller(chosen, pair)

  return issue_reporting.Read(chosen)


def _describe_matchpoints(matchpoints: float) -> str:
  """A matchpoint score, for a disagreement message."""
  return f'{matchpoints:g}'


def _describe_pair(pair: PairIdentity) -> str:
  """A pair as its number, side, and players, for a disagreement message."""
  players = ' & '.join(pair.names) if pair.names else 'unnamed'
  return f'{pair.number}{pair.side} ({players})'


def _describe_resolution(resolution: Resolution) -> str:
  """A played contract or a passout, for a disagreement message."""
  if isinstance(resolution, PlayedContract):
    contract = resolution.contract
    penalty = '' if contract.penalty == 'none' else f' {contract.penalty}'
    return (
      f'{contract.level}{contract.strain} by {contract.declarer}{penalty} '
      f'making {resolution.result.tricks_taken}'
    )
  return 'a passout'


def _describe_deal(deal: Deal) -> str:
  """A deal, named by its north hand alone.

  Spelling all four hands into a message that already carries another would bury
  the point; the north hand is enough to show two sources mean different deals,
  and both deals are on disk in full.
  """
  # TODO: name a seat the two sources actually differ on. Captures that agree on
  # north and differ elsewhere render as the same sentence twice, so the message
  # reports a contradiction without showing it. Doing it properly means letting
  # a describer see the sibling candidates, which `_agreed` deliberately does
  # not — it calls `describe` per value — so it wants that interface reworked
  # rather than a patch here.
  north_hand = deal.hands.get(Direction.NORTH)
  if not north_hand:
    return 'a deal stating no north hand'
  cards = ' '.join(f'{card.rank}{card.suit}' for card in north_hand.cards)
  return f'a deal holding {cards} in the north seat'


@dataclasses.dataclass(frozen=True)
class _SourceView:
  """What one traveller says about one board."""

  deal: Deal | None
  our_row: _OurRow | None
  # Whether this source recorded any play of the board at all. It tells a board
  # nobody reached from one we simply could not be found on, which read from
  # `our_row` alone look identical.
  has_results: bool
  # Whether any row named us, whether or not one could be singled out. A board
  # naming us twice yields no row and yet is not a board that failed to name us,
  # and reporting it as one would state the opposite of what happened.
  names_us: bool
  # What this source's account of the board cost to read. Carried per board
  # rather than raised against the session, so that a finding about a board the
  # sheet never played goes with the enrichment nothing consults.
  issues: tuple[Issue, ...] = ()


def _merge_board(
  board_number: int, views: Mapping[_Capture, _SourceView]
) -> BoardEnrichment:
  """Merge every source's account of one board into one enrichment.

  Each field is merged on its own, so a board whose sources agree on the deal
  and differ on the matchpoints keeps the deal. That matters for the club's two
  formats in particular: a PBN hand record lists every board dealt and no
  results at all, while the HTML recap covers only the boards actually reached —
  so the two routinely contribute different fields of the same board rather than
  contradicting each other.
  """
  # Built by loop rather than comprehension so that each mapping holds only the
  # captures that stated its field, at a value type that says so.
  deals: dict[_Capture, Deal] = {}
  rows: dict[_Capture, _OurRow] = {}
  for capture, view in views.items():
    if view.deal:
      deals[capture] = view.deal
    if view.our_row:
      rows[capture] = view.our_row

  matchpoints: dict[_Capture, float] = {}
  resolutions: dict[_Capture, Resolution] = {}
  for capture, row in rows.items():
    # Zero matchpoints is a real score — a board our pair was last on — so the
    # test is for a stated value rather than for a truthy one.
    if row.matchpoints is not None:
      matchpoints[capture] = row.matchpoints
    if row.result.resolution:
      resolutions[capture] = row.result.resolution

  # Merged one field at a time, each into a local of its own, so that a merge
  # takes its value type from the candidates handed to it rather than from the
  # field it will eventually fill.
  deal = _agreed(
    deals, field='deal', board_number=board_number, describe=_describe_deal
  )
  our_pair = _agreed_pair(
    {capture: row.our_pair for capture, row in rows.items()},
    field='our pair',
    board_number=board_number,
  )
  opponents = _agreed_pair(
    {capture: row.opponents for capture, row in rows.items()},
    field='opponents',
    board_number=board_number,
  )
  our_matchpoints = _agreed(
    matchpoints,
    field='our matchpoints',
    board_number=board_number,
    describe=_describe_matchpoints,
  )
  resolution = _agreed(
    resolutions,
    field='what we played',
    board_number=board_number,
    describe=_describe_resolution,
  )

  merged = (deal, our_pair, opponents, our_matchpoints, resolution)
  issues = [issue for field in merged for issue in field.issues]
  issues.extend(issue for view in views.values() for issue in view.issues)

  # A board that was played and yet yields no row of ours is the shape a
  # misspelled name takes, and the shape a traveller from the wrong session
  # takes on a board number the two sessions happen to share. A board nobody
  # reached yields no row either and is not worth remarking on, which is what
  # `has_results` separates. The finding rides on the enrichment rather than
  # being raised here, so it reaches a reviewer only if the sheet claims to have
  # played the board.
  if not rows and any(view.has_results for view in views.values()):
    # Named-but-ambiguous and never-named cost the board the same enrichment and
    # want different words: saying no row names us where several do would send a
    # reviewer looking for a misspelling that is not there.
    reason = (
      'every row of it that names us is one of several'
      if any(view.names_us for view in views.values())
      else 'no row of it names us'
    )
    issues.append(
      _OUR_ROW_NOT_FOUND.issue(
        f'board {board_number} was played and recorded, but {reason}, so '
        f'nothing about it could be joined'
      )
    )

  return BoardEnrichment(
    deal=deal.value,
    our_pair=our_pair.value,
    opponents=opponents.value,
    matchpoints=our_matchpoints.value,
    resolution=resolution.value,
    issues=tuple(issues),
  )


def build_enrichments(
  travellers: Sequence[Traveller], *, our_name: str
) -> issue_reporting.Read[Mapping[int, BoardEnrichment]]:
  """Merge every traveller of one session into per-board enrichments.

  Args:
    travellers: every capture covering the session, in any order. Two captures
      of one game are the ordinary case, whether or not they share a source;
      which captures cover a session is settled before this runs.
    our_name: the configured player name, as a capture prints it.

  Returns:
    One enrichment per board number any traveller covers, alongside issues for
    the boards naming us in several rows and the travellers naming us in none. A
    capture naming us nowhere is the shape a wrong-session capture takes, so it
    is reported against the session rather than against each of its boards in
    turn.
  """
  name_forms = _name_forms(our_name)
  issues: list[Issue] = []

  views: dict[int, dict[_Capture, _SourceView]] = {}
  for traveller in travellers:
    capture = _Capture(source=traveller.source, path=traveller.reference.path)
    names_us_anywhere = False

    for board in traveller.boards:
      row_match = _find_our_row(board, name_forms)
      names_us_anywhere = names_us_anywhere or row_match.value.names_us
      views.setdefault(board.number, {})[capture] = _SourceView(
        deal=board.deal,
        our_row=row_match.value.row,
        has_results=bool(board.results),
        names_us=row_match.value.names_us,
        issues=tuple(row_match.issues),
      )

    # A capture with no rows at all cannot name us, and says nothing about
    # whether it is the right session's; only one that had rows to look at
    # counts as having failed to find us.
    if not names_us_anywhere and any(
      board.results for board in traveller.boards
    ):
      issues.append(
        _TRAVELLER_NEVER_NAMES_US.issue(
          f'{capture} names {our_name!r} in no row of any board, so nothing '
          f'from it was joined; it may cover a different session'
        )
      )

  enrichments = {
    number: _merge_board(number, board_views)
    for number, board_views in sorted(views.items())
  }
  return issue_reporting.Read(enrichments, tuple(issues))


# --- cross-checks ---


def _contract_apart_from_declarer(
  contract: Contract,
) -> tuple[int, Strain, Penalty]:
  """What a contract says other than who played it.

  The declarer is separated out wherever two records are compared, because it is
  the field they disagree on for its own reasons: a traveller gets the seat
  wrong often enough that a mismatch there says something different from a
  mismatch in the level, the strain, or the doubling.
  """
  return (contract.level, contract.strain, contract.penalty)


def _cross_check(board: Board, enrichment: BoardEnrichment) -> Sequence[Issue]:
  """Compare what the sheet and the travellers each say we played.

  Only the fields both records carry are compared: the contract, the declarer,
  and the trick count. The matchpoints are not among them — the sheet has no
  matchpoint field at all, by design, because our own estimate of them is not
  worth storing (models.md `#vision-output`), so they are enrichment rather than
  a cross-check.

  Every disagreement is reported and none is resolved. The declarer is the field
  this matters most for: the validator cannot check it, because an auction
  written with implicit passes fixes no seats, and travellers get it wrong often
  enough that the sheet is not simply the suspect party.
  """
  sheet = board.outcome.resolution if board.outcome else None
  traveller = enrichment.resolution
  if not sheet or not traveller:
    return ()

  if isinstance(sheet, PlayedContract) != isinstance(traveller, PlayedContract):
    return (
      _PLAY_DISAGREEMENT.issue(
        f'the sheet records {_describe_resolution(sheet)} and the travellers '
        f'{_describe_resolution(traveller)}'
      ),
    )

  if not isinstance(sheet, PlayedContract) or not isinstance(
    traveller, PlayedContract
  ):
    # Both are passouts, which agree by being the same kind.
    return ()

  issues: list[Issue] = []

  # Compared apart from the declarer so that a misread strain and a misread seat
  # do not surface as one undifferentiated mismatch.
  if _contract_apart_from_declarer(
    sheet.contract
  ) != _contract_apart_from_declarer(traveller.contract):
    issues.append(
      _CONTRACT_DISAGREEMENT.issue(
        f'the sheet records {_describe_resolution(sheet)} and the travellers '
        f'{_describe_resolution(traveller)}'
      )
    )

  if sheet.contract.declarer != traveller.contract.declarer:
    issues.append(
      _DECLARER_DISAGREEMENT.issue(
        f'the sheet declares {sheet.contract.declarer} and the travellers '
        f'{traveller.contract.declarer}; neither is authoritative'
      )
    )

  if sheet.result.tricks_taken != traveller.result.tricks_taken:
    issues.append(
      _RESULT_DISAGREEMENT.issue(
        f'the sheet takes {sheet.result.tricks_taken} tricks and the '
        f'travellers {traveller.result.tricks_taken}'
      )
    )

  return tuple(issues)


# --- swap detection ---


def _count_agreement(board: Board, enrichment: BoardEnrichment) -> int:
  """How many independent signals put this sheet row against this board.

  Three signals, each worth one: the contract, the trick count, and whether the
  opening lead could have come from the hand that was on lead. The third is
  worth having precisely because it owes nothing to the traveller's result rows
  — it reads the sheet's own declarer against the traveller's deal, so it still
  speaks on a board where the traveller recorded no play at all.

  The contract is compared without its declarer, which the rest of this module
  treats as the field travellers most often get wrong (see `_cross_check`). A
  signal is only worth counting where disagreement means the rows are
  misaligned; a declarer the traveller simply has wrong would dock the correct
  pairing and let a coincidental neighbour win, which is the one mistake a swap
  suggestion must not make.

  A signal neither record supports counts for nothing rather than against, so a
  thinly recorded board simply scores low both ways and suggests no swap.
  """
  agreement = 0

  sheet = board.outcome.resolution if board.outcome else None
  traveller = enrichment.resolution
  if isinstance(sheet, PlayedContract) and isinstance(
    traveller, PlayedContract
  ):
    if _contract_apart_from_declarer(
      sheet.contract
    ) == _contract_apart_from_declarer(traveller.contract):
      agreement += 1
    if sheet.result == traveller.result:
      agreement += 1
  elif sheet and traveller and sheet.kind == traveller.kind:
    # Two passouts agree, and there is nothing further to compare.
    agreement += 1

  lead = board.opening_lead.card if board.opening_lead else None
  if enrichment.deal and lead and isinstance(sheet, PlayedContract):
    # The leading seat's hand has to be on hand for its silence to mean
    # anything: `find_lead_issues` reports nothing about a seat the deal states
    # no hand for, which read as a passing check would credit agreement to a
    # deal that said nothing either way.
    leader = sheet.contract.declarer.left_hand_opponent
    if enrichment.deal.hands.get(leader) and not deal_checks.find_lead_issues(
      enrichment.deal, declarer=sheet.contract.declarer, opening_lead=lead
    ):
      agreement += 1

  return agreement


@dataclasses.dataclass(frozen=True)
class _SwapCandidate:
  """Two sheet rows that would agree better with each other's board."""

  first: int
  second: int
  gain: int


def _find_likely_swaps(
  boards: Sequence[Board], enrichments: Mapping[int, BoardEnrichment]
) -> Mapping[int, _SwapCandidate]:
  """Sheet rows that line up better against each other's traveller board.

  Row-order mistakes are the expected failure mode — a pair of adjacent rows
  filled in the wrong order — so this searches transpositions rather than
  arbitrary permutations. Every pair of rows is weighed, not only adjacent ones,
  which costs nothing at a session's two dozen boards and catches a row written
  far out of place.

  A pair is suggested only when swapping strictly improves the agreement. Two
  boards whose play was identical score the same either way and so produce no
  suggestion, which is the honest answer: nothing in either record distinguishes
  them.

  Returns:
    The suggested swap for each sheet row that has one, keyed by index into
    `boards`. Each row appears in at most one suggestion — the pairing that
    gains most — so a genuine swap does not also drag its neighbours into
    overlapping suggestions that contradict each other.
  """
  numbered = [
    (index, board.number.schedule.number)
    for index, board in enumerate(boards)
    if board.number.schedule
  ]

  candidates: list[_SwapCandidate] = []
  for (first, first_number), (second, second_number) in itertools.combinations(
    numbered, 2
  ):
    if first_number not in enrichments or second_number not in enrichments:
      continue

    as_written = _count_agreement(
      boards[first], enrichments[first_number]
    ) + _count_agreement(boards[second], enrichments[second_number])
    if_swapped = _count_agreement(
      boards[first], enrichments[second_number]
    ) + _count_agreement(boards[second], enrichments[first_number])

    if if_swapped > as_written:
      candidates.append(
        _SwapCandidate(first=first, second=second, gain=if_swapped - as_written)
      )

  # Strongest first, so that when a row could pair with several the one it gains
  # most from wins and the weaker overlaps fall away.
  suggested: dict[int, _SwapCandidate] = {}
  for candidate in sorted(candidates, key=lambda pair: -pair.gain):
    if candidate.first in suggested or candidate.second in suggested:
      continue
    suggested[candidate.first] = candidate
    suggested[candidate.second] = candidate
  return suggested


def _swap_issue(
  boards: Sequence[Board], candidate: _SwapCandidate, index: int
) -> Issue:
  """Report one suggested swap against one of the two rows it involves.

  The claim the message makes is about the two rows together, because that is
  what was weighed: the pair is suggested when swapping improves their combined
  agreement, which one row can gain enough for to carry a small loss on the
  other. Saying instead that this row on its own agrees better with the other
  board would sometimes state the opposite of what was measured.
  """
  other = candidate.second if index == candidate.first else candidate.first
  this_number = boards[index].number.raw
  other_number = boards[other].number.raw
  return _LIKELY_ROW_SWAP.issue(
    f'this row and the row for board {other_number} agree better with each '
    f"other's traveller board than with their own, so boards {this_number} and "
    f'{other_number} were likely filled in the wrong order. Suggested only; '
    f'confirm against the scan before reordering'
  )


# --- the join ---


# Every code this phase attaches, its deal checks included. A run rewrites its
# own findings from scratch, so what a previous run left behind is dropped
# first: re-running over a session already reconciled is the ordinary way a
# later traveller is taken in, and appending would leave a second copy of every
# finding on a record where nothing had changed.
#
# This is what makes an issue code load-bearing rather than decorative: a code
# here that another stage also used would see that stage's findings deleted on
# every run. Codes are unique across the pipeline today — parsing, validation,
# the capture parsers, and this phase share none — and a new `Failure` anywhere
# has to keep it that way.
_OUR_CODES = deal_checks.CODES | {
  failure.code
  for failure in (
    _OUR_ROW_NOT_FOUND,
    _OUR_ROW_AMBIGUOUS,
    _TRAVELLER_NEVER_NAMES_US,
    _BOARD_NOT_IN_TRAVELLERS,
    _SOURCES_DISAGREE,
    _CONTRACT_DISAGREEMENT,
    _DECLARER_DISAGREEMENT,
    _RESULT_DISAGREEMENT,
    _PLAY_DISAGREEMENT,
    _LIKELY_ROW_SWAP,
  )
}


def _findings_of_other_stages(issues: Iterable[Issue]) -> tuple[Issue, ...]:
  """What a record carries from every stage but this one."""
  return tuple(issue for issue in issues if issue.code not in _OUR_CODES)


def _enrich(board: Board, enrichment: BoardEnrichment) -> Board:
  """Copy the traveller-sourced fields onto a board, with its findings.

  The reconciled subset is copied onto the board rather than left to be looked
  up, so that the stored session stays self-contained for the analysis stage.
  The par is deliberately not among it: one par serves every table that played
  the board, so it stays in the traveller record and is read from there.
  """
  issues = [
    *_findings_of_other_stages(board.issues),
    *enrichment.issues,
    *_cross_check(board, enrichment),
  ]
  if enrichment.deal:
    issues.extend(deal_checks.find_deal_issues(enrichment.deal))

    lead = board.opening_lead.card if board.opening_lead else None
    sheet = board.outcome.resolution if board.outcome else None
    # Checked against the sheet's own declarer: the lead is the sheet's, so
    # pairing the two tests the sheet against the deal rather than against the
    # traveller's account of who played the hand.
    if lead and isinstance(sheet, PlayedContract):
      issues.extend(
        deal_checks.find_lead_issues(
          enrichment.deal,
          declarer=sheet.contract.declarer,
          opening_lead=lead,
        )
      )

  return board.model_copy(
    update={
      'deal': enrichment.deal,
      'our_pair': enrichment.our_pair,
      'opponents': enrichment.opponents,
      'matchpoints': enrichment.matchpoints,
      'issues': tuple(issues),
    }
  )


def _without_enrichment(session: Session) -> Session:
  """The session with everything reconciliation owns taken back off it.

  The counterpart to enriching: it undoes what a previous run wrote, so that
  re-running against no travellers leaves the same record a sheet that was never
  reconciled would have. Findings from parsing and validation stay — this owns
  the traveller-sourced fields and its own codes, and nothing else.

  Clearing is safe only while this phase is the sole writer of those fields, and
  it is today. A second writer — a review UI letting a person fill a deal by
  hand — would have its work deleted here, because nothing in the model tells a
  typed value from a traveller-sourced one. See tasks.md
  `#corrections-survive-rerun`, which has to land before hand-editing does.
  """
  boards = tuple(
    board.model_copy(
      update={
        'deal': None,
        'our_pair': None,
        'opponents': None,
        'matchpoints': None,
        'issues': _findings_of_other_stages(board.issues),
      }
    )
    for board in session.boards
  )
  return session.model_copy(
    update={
      'boards': boards,
      'source': session.source.model_copy(update={'travellers': ()}),
      'issues': _findings_of_other_stages(session.issues),
    }
  )


def reconcile_session(
  session: Session, travellers: Sequence[Traveller], *, our_name: str
) -> Session:
  """Join a digitized session to its travellers and return the enriched record.

  Runs to completion whatever it is given. With no travellers the session comes
  back unenriched, which is the ordinary state of a session whose results were
  never published — travellers.md `#graceful-degradation` covers what that
  costs, and finalizing such a session is the review stage's escape hatch rather
  than a failure here.

  Args:
    session: the digitized sheet, as parsed and validated.
    travellers: every traveller covering the same session, in any order.
    our_name: the configured player name, used to find our row.

  Returns:
    A copy of the session with each board enriched and every finding attached —
    board-level findings on the board, and findings about a whole capture on the
    session. `source.travellers` records the captures consulted.
  """
  if not travellers:
    # Unenriched rather than untouched. On a sheet no run has reconciled the two
    # are the same thing, but on one an earlier run enriched they are not: a
    # capture withdrawn as the wrong session's has to take its deal, its
    # matchpoints, its pair identities, and its findings with it, or the record
    # would keep asserting what nothing now supports.
    return _without_enrichment(session)

  enrichments = build_enrichments(travellers, our_name=our_name)
  swaps = _find_likely_swaps(session.boards, enrichments.value)

  boards: list[Board] = []
  for index, board in enumerate(session.boards):
    schedule = board.number.schedule
    enrichment = enrichments.value.get(schedule.number) if schedule else None

    if not enrichment:
      # An unreadable board number already carries its own issue from parsing;
      # this says what that cost, which is the whole of the board's enrichment.
      reason = (
        f'board {board.number.raw} appears in no traveller'
        if schedule
        else "this row's board number could not be read"
      )
      board = board.model_copy(
        update={
          'issues': (
            *_findings_of_other_stages(board.issues),
            _BOARD_NOT_IN_TRAVELLERS.issue(
              f'{reason}, so it goes unenriched — no deal, no matchpoints, and '
              f'no pair identities'
            ),
          )
        }
      )
    else:
      board = _enrich(board, enrichment)

    if index in swaps:
      board = board.model_copy(
        update={
          'issues': (
            *board.issues,
            _swap_issue(session.boards, swaps[index], index),
          )
        }
      )

    boards.append(board)

  source = session.source.model_copy(
    update={
      'travellers': tuple(traveller.reference for traveller in travellers)
    }
  )
  return session.model_copy(
    update={
      'boards': tuple(boards),
      'source': source,
      'issues': (
        *_findings_of_other_stages(session.issues),
        *enrichments.issues,
      ),
    }
  )
