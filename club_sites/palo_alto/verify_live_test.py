# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
"""Tests for the live-site check's request guard.

The guard keeps the live check from ever booking a game, so its rule is tested
on its own, without a browser or the network.
"""

import json

import pytest
from verify_live import RequestSummary, is_allowed, requested_action

# --- requested_action ---


def test_a_json_body_names_its_action() -> None:
  body = json.dumps({'action': 'keyword', 'value': 'First Last'}).encode()

  assert requested_action(body) == 'keyword'


def test_a_missing_body_names_no_action() -> None:
  assert requested_action(None) is None


def test_a_form_encoded_body_names_no_action() -> None:
  # Only a JSON body is parsed, since the site's data calls send JSON.
  assert requested_action(b'action=keyword&value=First') is None


def test_a_body_that_is_not_utf8_names_no_action() -> None:
  assert requested_action(b'\xff\xfe\xfa') is None


def test_a_json_body_that_is_not_an_object_names_no_action() -> None:
  assert requested_action(json.dumps(['keyword']).encode()) is None


def test_a_body_with_a_non_string_action_names_no_action() -> None:
  assert requested_action(json.dumps({'action': 7}).encode()) is None


# --- is_allowed: page loading ---


def test_the_reservations_page_loads() -> None:
  request = RequestSummary(
    method='GET',
    resource_type='document',
    url='https://paloaltobridge.org/reservations/',
    action=None,
  )

  assert is_allowed(request)


def test_any_other_document_is_refused() -> None:
  # A link or frame elsewhere on the site could be a save sent by GET.
  request = RequestSummary(
    method='GET',
    resource_type='document',
    url='https://paloaltobridge.org/reservations/save?game=1',
    action=None,
  )

  assert not is_allowed(request)


@pytest.mark.parametrize(
  'resource_type', ['script', 'stylesheet', 'image', 'font', 'media']
)
def test_page_building_resources_load_from_any_host(resource_type: str) -> None:
  request = RequestSummary(
    method='GET',
    resource_type=resource_type,
    url='https://cdn.example.com/asset',
    action=None,
  )

  assert is_allowed(request)


# --- is_allowed: data calls ---


@pytest.mark.parametrize('resource_type', ['fetch', 'xhr', 'ping', 'other'])
def test_a_get_data_call_is_refused(resource_type: str) -> None:
  # Even a lookup is refused when sent by GET: data calls pass only as POSTs.
  request = RequestSummary(
    method='GET',
    resource_type=resource_type,
    url='https://paloaltobridge.org/action.php?action=keyword',
    action=None,
  )

  assert not is_allowed(request)


def test_a_read_action_posted_to_the_site_passes() -> None:
  request = RequestSummary(
    method='POST',
    resource_type='fetch',
    url='https://paloaltobridge.org/reservations/action.php',
    action='keyword',
  )

  assert is_allowed(request)


def test_an_unlisted_action_is_refused() -> None:
  request = RequestSummary(
    method='POST',
    resource_type='fetch',
    url='https://paloaltobridge.org/reservations/action.php',
    action='saveReservation',
  )

  assert not is_allowed(request)


def test_a_post_naming_no_action_is_refused() -> None:
  request = RequestSummary(
    method='POST',
    resource_type='fetch',
    url='https://paloaltobridge.org/reservations/action.php',
    action=None,
  )

  assert not is_allowed(request)


def test_a_read_action_posted_to_another_endpoint_is_refused() -> None:
  request = RequestSummary(
    method='POST',
    resource_type='fetch',
    url='https://paloaltobridge.org/reservations/save.php',
    action='keyword',
  )

  assert not is_allowed(request)


def test_a_read_action_posted_to_another_host_is_refused() -> None:
  request = RequestSummary(
    method='POST',
    resource_type='fetch',
    url='https://example.com/action.php',
    action='keyword',
  )

  assert not is_allowed(request)


@pytest.mark.parametrize('method', ['PUT', 'PATCH', 'DELETE', 'HEAD'])
def test_other_methods_are_refused(method: str) -> None:
  request = RequestSummary(
    method=method,
    resource_type='fetch',
    url='https://paloaltobridge.org/reservations/action.php',
    action='keyword',
  )

  assert not is_allowed(request)
