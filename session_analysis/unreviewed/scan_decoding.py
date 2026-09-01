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

Multi-page scans are not yet supported. spec.md allows one sheet to span several
pages, but what a second page means is unsettled — a retake to choose among, a
half of one grid to stitch, or a second sheet — and each answer implies
different code. Until a real multi-page scan exists to settle it, the first page
is read and the rest are reported; tasks.md `#multi-page-scans` carries the
question.

The capture date comes from the file's own metadata, never the clock. A scan
reprocessed months later must resolve its footer against the day it was taken,
or the year silently shifts.
"""

import dataclasses
import datetime
from pathlib import Path

import pypdf
from PIL import Image, ImageOps, UnidentifiedImageError

from session_analysis import issue_reporting
from session_analysis.enums import IssueSeverity
from session_analysis.models import Issue

# Reported rather than raised: the first page still digitizes, so the run keeps
# going and a person decides whether the rest held anything worth having.
_EXTRA_SCAN_PAGES = issue_reporting.Failure(
  'extra_scan_pages', IssueSeverity.MEDIUM, 'scan'
)
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

  Covers a file that is not an image or PDF at all, one too damaged to read, and
  a PDF page holding anything other than a single embedded image. Ingest treats
  it as terminal for that scan: the file moves out of the inbox rather than
  being retried on the next run.
  """


@dataclasses.dataclass(frozen=True)
class DecodedScan:
  """One scan file, read into what the pipeline downstream of it needs."""

  image: Image.Image
  # The day the scan was taken, which fixes the year on a footer that writes
  # only a month and day. See the module docstring on why this is never today.
  captured_on: datetime.date


@dataclasses.dataclass(frozen=True)
class _ScanContents:
  """What one format's reader recovers, before the date fallback applies."""

  image: Image.Image
  # None when the file stated no capture date of its own.
  stated_date: datetime.date | None


def decode_scan(path: Path) -> issue_reporting.Read[DecodedScan]:
  """Read a scan file into its image and the day it was captured.

  Raises:
    ScanDecodingError: the file yielded no image to transcribe.
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

  decoded = DecodedScan(image=contents.value.image, captured_on=captured_on)
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
    image=uprighted, stated_date=_exif_capture_date(image)
  )
  return issue_reporting.Read(contents)


def _read_pdf(path: Path) -> issue_reporting.Read[_ScanContents]:
  """Unwrap the image a scanner app's PDF holds on its first page."""
  try:
    reader = pypdf.PdfReader(path)
    pages = reader.pages
  except (pypdf.errors.PdfReadError, OSError) as error:
    raise ScanDecodingError(
      f'could not read {path.name} as a PDF: {error}'
    ) from error

  if not pages:
    raise ScanDecodingError(f'{path.name} is a PDF holding no pages')

  embedded = pages[0].images
  if len(embedded) != 1:
    raise ScanDecodingError(
      f"{path.name}'s first page holds {len(embedded)} embedded images, not "
      f'one, so which of them is the sheet cannot be told'
    )

  # pypdf decodes an embedded image lazily, and hands back None for one whose
  # filter or colour space it cannot turn into pixels.
  image = embedded[0].image
  if not image:
    raise ScanDecodingError(
      f"{path.name}'s embedded image could not be decoded to pixels"
    )

  issues: tuple[Issue, ...] = ()
  if len(pages) > 1:
    issues = (
      _EXTRA_SCAN_PAGES.issue(
        f'{path.name} holds {len(pages)} pages; only the first was digitized, '
        f'since what a further page means is not yet settled'
      ),
    )

  contents = _ScanContents(image=image, stated_date=_pdf_capture_date(reader))
  return issue_reporting.Read(contents, issues)


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
