# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for reading a scan file into an image and a capture date.

Scans are written to real temporary paths rather than a fake filesystem: this
module's subject is files, and Pillow's encoders reach the disk below anything a
filesystem fake patches (see faking-the-filesystem.md).
"""

import datetime
import os
from collections.abc import Sequence
from pathlib import Path

import pypdf
import pytest
from PIL import Image

from session_analysis import issue_reporting
from session_analysis.unreviewed.scan_decoding import (
  DecodedScan,
  ScanDecodingError,
  UndecodedPage,
  decode_scan,
)

# EXIF spells a timestamp with colons in the date half.
_EXIF_TIMESTAMP_FORMAT = '%Y:%m:%d %H:%M:%S'
_DATE_TIME = 306
_DATE_TIME_ORIGINAL = 36867
_ORIENTATION = 274
_EXIF_SUB_IFD = 0x8769


def _sheets(
  decoded: issue_reporting.Read[Sequence[DecodedScan | UndecodedPage]],
) -> list[DecodedScan]:
  """The pages of a read that yielded a sheet."""
  return [one for one in decoded.value if isinstance(one, DecodedScan)]


def _write_photo(
  path: Path,
  *,
  size: tuple[int, int] = (40, 60),
  taken: datetime.datetime | None = None,
  written: datetime.datetime | None = None,
  orientation: int | None = None,
) -> Path:
  """Write a JPEG scan carrying whatever EXIF a test wants it to state.

  JPEG rather than PNG because the Exif sub-IFD that holds `DateTimeOriginal`
  only survives a round trip through it — and because a phone scanner writes
  JPEG anyway. The compression is irrelevant here: nothing in this module reads
  the pixels beyond their size.
  """
  image = Image.new('L', size, 255)
  exif = image.getexif()
  if written:
    exif[_DATE_TIME] = written.strftime(_EXIF_TIMESTAMP_FORMAT)
  if taken:
    exif.get_ifd(_EXIF_SUB_IFD)[_DATE_TIME_ORIGINAL] = taken.strftime(
      _EXIF_TIMESTAMP_FORMAT
    )
  if orientation:
    exif[_ORIENTATION] = orientation
  image.save(path, exif=exif)
  return path


def _write_pdf(
  path: Path,
  *,
  pages: int = 1,
  created: str | None = None,
  size: tuple[int, int] = (40, 60),
) -> Path:
  """Write a PDF wrapping one image per page, as a scanner app produces."""
  drawn = [Image.new('RGB', size, 'white') for _ in range(pages)]
  drawn[0].save(path, save_all=True, append_images=drawn[1:])
  if created:
    writer = pypdf.PdfWriter(clone_from=path)
    writer.add_metadata({'/CreationDate': created})
    with path.open('wb') as handle:
      writer.write(handle)
  return path


def _set_modification_day(path: Path, day: datetime.date) -> None:
  """Set a file's modification time to noon on `day`."""
  when = datetime.datetime.combine(day, datetime.time(12)).timestamp()
  os.utime(path, (when, when))


# --- reading a photograph ---


def test_a_photo_is_read_at_the_size_it_was_written(tmp_path: Path) -> None:
  scan = _write_photo(tmp_path / 'scan.jpg', size=(40, 60))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].image.size == (40, 60)


def test_the_capture_date_comes_from_when_the_shutter_fired(
  tmp_path: Path,
) -> None:
  scan = _write_photo(
    tmp_path / 'scan.jpg', taken=datetime.datetime(2026, 6, 29, 11, 30)
  )
  # A later modification day, which must not win: the scan is what dates the
  # session, not whenever the file was last touched.
  _set_modification_day(scan, datetime.date(2026, 9, 1))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)
  assert not decoded.issues


def test_the_written_date_stands_in_when_no_original_was_recorded(
  tmp_path: Path,
) -> None:
  scan = _write_photo(
    tmp_path / 'scan.jpg', written=datetime.datetime(2026, 6, 29, 11, 30)
  )

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)


def test_a_photo_stating_no_date_falls_back_to_its_modification_day(
  tmp_path: Path,
) -> None:
  scan = _write_photo(tmp_path / 'scan.jpg')
  _set_modification_day(scan, datetime.date(2026, 6, 29))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)
  # Reported, because the fallback is a guess: a file synced long after the
  # session carries the wrong day, and the footer's year rides on it.
  assert [issue.code for issue in decoded.issues] == ['undated_scan']


def test_an_unreadable_timestamp_falls_back_like_a_missing_one(
  tmp_path: Path,
) -> None:
  image = Image.new('L', (40, 60), 255)
  exif = image.getexif()
  exif[_DATE_TIME] = 'sometime last Tuesday'
  scan = tmp_path / 'scan.jpg'
  image.save(scan, exif=exif)
  _set_modification_day(scan, datetime.date(2026, 6, 29))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)
  assert [issue.code for issue in decoded.issues] == ['undated_scan']


def test_a_sideways_photo_is_uprighted_by_its_orientation_tag(
  tmp_path: Path,
) -> None:
  # Orientation 6 means "rotate 90° clockwise to display": a phone writes the
  # tag rather than rotating pixels, so grid detection would see it on its side.
  scan = _write_photo(tmp_path / 'scan.jpg', size=(40, 60), orientation=6)

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].image.size == (60, 40)


def test_a_file_that_is_no_image_at_all_is_refused(tmp_path: Path) -> None:
  scan = tmp_path / 'scan.jpg'
  scan.write_text('not an image')

  with pytest.raises(ScanDecodingError, match='could not read'):
    decode_scan(scan)


# --- unwrapping a PDF ---


def test_a_pdf_yields_the_image_it_wraps(tmp_path: Path) -> None:
  scan = _write_pdf(tmp_path / 'scan.pdf', size=(40, 60))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].image.size == (40, 60)


def test_a_pdf_capture_date_comes_from_its_own_metadata(
  tmp_path: Path,
) -> None:
  scan = _write_pdf(tmp_path / 'scan.pdf', created="D:20260629113000-07'00'")
  _set_modification_day(scan, datetime.date(2026, 9, 1))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)
  assert not decoded.issues


def test_a_pdf_whose_stated_date_is_unreadable_falls_back(
  tmp_path: Path,
) -> None:
  # A PDF writer stamps `/CreationDate` for itself, so a PDF stating no date at
  # all barely arises; one stating a date nothing can parse is the case worth
  # covering, and it degrades the same way.
  scan = _write_pdf(tmp_path / 'scan.pdf', created='sometime last Tuesday')
  _set_modification_day(scan, datetime.date(2026, 6, 29))

  decoded = decode_scan(scan)

  assert _sheets(decoded)[0].captured_on == datetime.date(2026, 6, 29)
  assert [issue.code for issue in decoded.issues] == ['undated_scan']


def test_every_page_of_a_container_is_its_own_sheet(
  tmp_path: Path,
) -> None:
  # A scanner app writes one file per feed, so sheets fed together arrive in one
  # container and each is a separate session.
  scan = _write_pdf(tmp_path / 'scan.pdf', pages=3, size=(40, 60))

  decoded = decode_scan(scan)

  assert len(decoded.value) == 3
  assert [sheet.page for sheet in _sheets(decoded)] == [1, 2, 3]
  assert all(sheet.image.size == (40, 60) for sheet in _sheets(decoded))


def test_a_containers_pages_share_its_capture_date(
  tmp_path: Path,
) -> None:
  # They were fed to the scanner together, so the file's own date is every
  # sheet's — and it is what fixes the year on each footer.
  scan = _write_pdf(
    tmp_path / 'scan.pdf', pages=2, created="D:20260629114500-07'00'"
  )

  decoded = decode_scan(scan)

  assert [sheet.captured_on for sheet in _sheets(decoded)] == [
    datetime.date(2026, 6, 29),
    datetime.date(2026, 6, 29),
  ]


def test_a_photo_is_always_page_one(tmp_path: Path) -> None:
  scan = _write_photo(tmp_path / 'scan.jpg', size=(40, 60))

  decoded = decode_scan(scan)

  assert [sheet.page for sheet in _sheets(decoded)] == [1]


def test_a_page_holding_several_images_fails_only_that_page(
  tmp_path: Path,
) -> None:
  # Which of the two embedded images is the sheet cannot be told, so nothing is
  # guessed — and the failure is the page's, not the file's.
  first = _write_pdf(tmp_path / 'first.pdf')
  second = _write_pdf(tmp_path / 'second.pdf')
  writer = pypdf.PdfWriter(clone_from=first)
  writer.pages[0].merge_page(pypdf.PdfReader(second).pages[0])
  scan = tmp_path / 'scan.pdf'
  with scan.open('wb') as handle:
    writer.write(handle)

  decoded = decode_scan(scan)

  assert not _sheets(decoded)
  undecoded = [
    read for read in decoded.value if isinstance(read, UndecodedPage)
  ]
  assert [page.page for page in undecoded] == [1]
  assert 'embedded images' in undecoded[0].reason


def test_a_bad_page_does_not_cost_the_sheets_around_it(
  tmp_path: Path,
) -> None:
  # An app that appends a summary page, or a form with a logo beside the sheet,
  # should not lose the pages that read cleanly.
  spoiled = _write_pdf(tmp_path / 'spoiled.pdf')
  extra = _write_pdf(tmp_path / 'extra.pdf')
  writer = pypdf.PdfWriter(clone_from=_write_pdf(tmp_path / 'feed.pdf'))
  writer.append(spoiled)
  writer.pages[1].merge_page(pypdf.PdfReader(extra).pages[0])
  scan = tmp_path / 'scan.pdf'
  with scan.open('wb') as handle:
    writer.write(handle)

  decoded = decode_scan(scan)

  assert [sheet.page for sheet in _sheets(decoded)] == [1]
  assert [
    read.page for read in decoded.value if isinstance(read, UndecodedPage)
  ] == [2]


def test_a_file_that_is_no_pdf_at_all_is_refused(tmp_path: Path) -> None:
  scan = tmp_path / 'scan.pdf'
  scan.write_text('not a pdf')

  with pytest.raises(ScanDecodingError, match='could not read'):
    decode_scan(scan)
