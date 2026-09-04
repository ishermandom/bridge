# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Reading a scan file into the image and the date extraction needs.

A scan arrives as whatever the phone's scanner app produced — a photo, or a PDF
wrapping one. Extraction wants neither: `transcribe_sheet` takes a decoded
`Image`, and assembly wants the day the sheet was scanned, to resolve the year a
footer's `6/29` leaves off. This module is the step between, and the only one
that opens a scan file at all.

A PDF is unwrapped rather than rasterized. A scanner app's PDF is a container
around the photo it already took, so pulling that image out returns the original
pixels, where rendering the page would resample them. A PDF page that does not
hold exactly one image is refused rather than guessed at — nothing here can say
which of several images is the sheet.

Every page of a container is its own sheet. A scanner app writes one PDF per
feed, so several sheets scanned together arrive in one file, and each is a
separate session with its own footer, key and traveller. A page that cannot be
decoded is reported as itself and the rest go on — a page that wraps two images
because the app appended a summary should not cost the sheets around it. A file
that will not open at all is different, and raises.

The capture date comes from the file's own metadata, never the clock. A scan
reprocessed months later must resolve its footer against the day it was taken,
or the year silently shifts.
"""

import dataclasses
import datetime
from collections.abc import Sequence
from pathlib import Path

import pypdf
from PIL import Image, ImageOps, UnidentifiedImageError

from session_analysis import issue_reporting
from session_analysis.enums import IssueSeverity

# The file stated no capture date, so its modification time stood in. Usually
# right — a scan reaches the inbox minutes after it is taken — but a file copied
# or re-synced long afterwards carries the wrong day, and the footer's year
# rides on it.
_UNDATED_SCAN = issue_reporting.Failure(
  'undated_scan', IssueSeverity.MEDIUM, 'scan'
)

_PDF_SUFFIX = '.pdf'

# EXIF's own date spelling, colon-separated in the date half: `2026:06:29
# 11:30:00`.
_EXIF_TIMESTAMP_FORMAT = '%Y:%m:%d %H:%M:%S'
# `DateTime`, in the top-level IFD: when the file was written.
_EXIF_DATE_TIME = 306
# `DateTimeOriginal`, in the Exif sub-IFD: when the shutter fired. Preferred,
# since an app that rewrites the file leaves it alone.
_EXIF_DATE_TIME_ORIGINAL = 36867
_EXIF_SUB_IFD = 0x8769


class ScanDecodingError(Exception):
  """Raised when a scan file yields no image to transcribe.

  Covers a file that is not an image or PDF at all, and one too damaged to open.
  A single page that yields nothing is not among them — that is reported as the
  page's own failure, leaving the rest of the container readable. Ingest treats
  this as terminal for the scan: the file moves out of the inbox rather than
  being retried on the next run.
  """


@dataclasses.dataclass(frozen=True)
class UndecodedPage:
  """One page of a container that yielded no image, and why."""

  page: int
  reason: str


@dataclasses.dataclass(frozen=True)
class DecodedScan:
  """One sheet, read into what the pipeline downstream of it needs."""

  image: Image.Image
  # The day the scan was taken, which fixes the year on a footer that writes
  # only a month and day. See the module docstring on why this is never today.
  captured_on: datetime.date
  # Which page of the file this sheet came from, counting from one. A
  # single-image scan is always page one.
  page: int


@dataclasses.dataclass(frozen=True)
class _ScanContents:
  """What one format's reader recovers, before the date fallback applies."""

  # One per page in the file, in order: the image it wrapped, or why it did not
  # yield one.
  pages: tuple[Image.Image | str, ...]
  # None when the file stated no capture date of its own. A container's pages
  # share it: they were fed to the scanner together.
  stated_date: datetime.date | None


def decode_scan(
  path: Path,
) -> issue_reporting.Read[Sequence[DecodedScan | UndecodedPage]]:
  """Read a scan file into one decoded sheet per page it holds.

  Returns:
    One entry per page, in order — a `DecodedScan` for a page that yielded a
    sheet, an `UndecodedPage` for one that did not. A photo yields a single
    entry; a container yields as many as it holds, since a scanner app writes
    one file per feed and each sheet in that feed is its own session.

  Raises:
    ScanDecodingError: the file could not be opened at all, so there are no
      pages to report on.
  """
  is_pdf = path.suffix.lower() == _PDF_SUFFIX
  contents = _read_pdf(path) if is_pdf else _read_image(path)

  issues = list(contents.issues)
  captured_on = contents.value.stated_date
  if not captured_on:
    # `st_mtime` is the closest thing left to a capture time. It is a guess, so
    # it is reported as one rather than passed off as the file's own answer.
    captured_on = datetime.date.fromtimestamp(path.stat().st_mtime)
    issues.append(
      _UNDATED_SCAN.issue(
        f'{path.name} states no capture date; read its modification day '
        f'({captured_on}) instead, which fixes the footer year'
      )
    )

  decoded = tuple(
    UndecodedPage(page=page, reason=read)
    if isinstance(read, str)
    else DecodedScan(image=read, captured_on=captured_on, page=page)
    for page, read in enumerate(contents.value.pages, start=1)
  )
  return issue_reporting.Read(decoded, tuple(issues))


def _read_image(path: Path) -> issue_reporting.Read[_ScanContents]:
  """Read a photo, uprighted by the orientation its camera recorded.

  A phone writes the sensor's own orientation into EXIF rather than rotating the
  pixels, so a sheet photographed in portrait can arrive on its side. Grid
  detection would fail on it, and confusingly — so the rotation is applied here,
  where the EXIF is already open.
  """
  try:
    image = Image.open(path)
    image.load()
  except (UnidentifiedImageError, OSError) as error:
    raise ScanDecodingError(
      f'could not read {path.name} as an image: {error}'
    ) from error

  # `exif_transpose` hands back None only when asked to work in place, which
  # this is not, so the upright image is always there.
  uprighted = ImageOps.exif_transpose(image)
  assert uprighted is not None
  contents = _ScanContents(
    pages=(uprighted,), stated_date=_exif_capture_date(image)
  )
  return issue_reporting.Read(contents)


def _read_pdf(path: Path) -> issue_reporting.Read[_ScanContents]:
  """Unwrap the image each page of a scanner app's PDF wraps."""
  try:
    reader = pypdf.PdfReader(path)
    pages = reader.pages
  except (pypdf.errors.PdfReadError, OSError) as error:
    raise ScanDecodingError(
      f'could not read {path.name} as a PDF: {error}'
    ) from error

  if not pages:
    raise ScanDecodingError(f'{path.name} is a PDF holding no pages')

  # Every page is decoded here rather than as the caller reaches it, so the
  # whole container's pixels are resident at once — around 25MB a sheet at
  # letter size and 300 dpi. Fine for the feeds in hand; a feed of twenty would
  # want the pages decoded one at a time, which means handing back something
  # lazier than a sequence and keeping `PdfReader`'s stream open across it.
  contents = _ScanContents(
    pages=tuple(
      _page_image(page, number) for number, page in enumerate(pages, start=1)
    ),
    stated_date=_pdf_capture_date(reader),
  )
  return issue_reporting.Read(contents)


def _page_image(page: pypdf.PageObject, number: int) -> Image.Image | str:
  """The single embedded image one page wraps, or why it yielded none.

  A page's own failure rather than the file's: an app that appends a summary
  page, or a form with a logo beside the sheet, should not cost the sheets
  around it. That holds for a page pypdf cannot read at all, so the reasons it
  raises for are answered here rather than left to escape — uncaught, one such
  page would abort the run and stay in the inbox, and every later run would
  abort on it again.
  """
  # `page.images` walks the page's resources and raises on an inline image or a
  # malformed XObject; `.image` decodes lazily and raises on a filter or colour
  # space pypdf has no reader for. Pillow raises its own on bytes that survive
  # that far and still will not decode.
  try:
    embedded = page.images
    if len(embedded) != 1:
      return (
        f'page {number} holds {len(embedded)} embedded images, not one, so '
        f'which of them is the sheet cannot be told'
      )
    image = embedded[0].image
  except (
    KeyError,
    NotImplementedError,
    OSError,
    ValueError,
    pypdf.errors.PdfReadError,
  ) as error:
    return f'page {number} could not be read: {type(error).__name__}: {error}'

  # pypdf hands back None rather than raising for an image it decoded to
  # nothing.
  if not image:
    return f'the image embedded on page {number} could not be decoded to pixels'
  return image


def _exif_capture_date(image: Image.Image) -> datetime.date | None:
  """The day a photo's EXIF says it was taken, or None if it says nothing."""
  exif = image.getexif()
  # `DateTimeOriginal` first: it records the shutter, and survives an app
  # rewriting the file in a way the top-level `DateTime` does not.
  written = exif.get_ifd(_EXIF_SUB_IFD).get(_EXIF_DATE_TIME_ORIGINAL)
  return _exif_date(written) or _exif_date(exif.get(_EXIF_DATE_TIME))


def _exif_date(written: object) -> datetime.date | None:
  """One EXIF timestamp as a date, or None if it is absent or malformed."""
  if not isinstance(written, str):
    return None
  try:
    return datetime.datetime.strptime(written, _EXIF_TIMESTAMP_FORMAT).date()
  except ValueError:
    # A camera that wrote a timestamp we cannot read is no worse than one that
    # wrote none: both fall through to the file's modification day, which is
    # reported.
    return None


def _pdf_capture_date(reader: pypdf.PdfReader) -> datetime.date | None:
  """The day a PDF's metadata says it was made, or None if it says nothing."""
  metadata = reader.metadata
  if not metadata:
    return None
  try:
    created = metadata.creation_date
  except ValueError:
    # `/CreationDate` is free text in the file; pypdf raises rather than
    # returning None when it does not parse as a PDF date.
    return None
  return created.date() if created else None
