#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Sets up the machine:
#
# - Hangover, which runs Windows programs on ARM Linux by translating their
#   Intel code;
# - AutoHotkey, a Windows program that drives SuitPlay's window;
# - Chrome for Testing, the browser the ACBL fetch drives;
# - a virtual display for each job's windows;
# - the idle check, which powers the machine off once nothing needs it.
#
# Lima runs this as root on every boot, so each step skips work already done. By
# then Lima has written the files `lima.yaml` names, among them the units
# `start_services` enables.

hangover_version=11.16
hangover_archive="hangover_${hangover_version}_debian13_trixie_arm64.tar"
hangover_url="https://github.com/AndreRH/hangover/releases/download/hangover-${hangover_version}/${hangover_archive}"
hangover_sha256=b5493f5903ab3c05f78bf4c03b06ac0005eb26f732437748c1592fefa45e861a

autohotkey_version=2.0.30
autohotkey_url="https://github.com/AutoHotkey/AutoHotkey/releases/download/v${autohotkey_version}/AutoHotkey_${autohotkey_version}.zip"
autohotkey_sha256=1e0ece7ecb2d5646e55758150472677996a57f9db5c83d2996d8b47b9e2f31a4
autohotkey_dir=/opt/autohotkey

chrome_version=157.0.8103.50
chrome_url="https://storage.googleapis.com/chrome-for-testing-public/${chrome_version}/linux-arm64/chrome-linux-arm64.zip"
chrome_sha256=9539c1612121eb09c4b787f4f9d0c732357772eb22583620ffed64d50dd6c4cc
# The ACBL fetch launches `chrome` from here.
chrome_dir=/opt/chrome-linux-arm64

# Virtual displays, screenshots of them for debugging, and a tool to unpack
# AutoHotkey's and Chrome's archives.
debian_packages=(xvfb scrot unzip)

# Stop with a message naming the step that failed.
fail() {
  echo "setup.sh: $1" >&2
  exit 1
}

# Download `$1` to `$3`, and check it against the SHA-256 digest `$2`.
download_verified() {
  local url=$1
  local sha256=$2
  local path=$3
  curl --fail --silent --show-error --location --output "$path" "$url" \
    || fail "downloading $url failed"
  # `sha256sum --check` reads `<digest>  <path>` lines from standard input.
  echo "$sha256  $path" | sha256sum --check --quiet \
    || fail "$url doesn't match its pinned digest"
}

# Install the Debian packages and Hangover, unless Hangover's `wine` is already
# there.
install_packages() {
  if command -v wine > /dev/null; then
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update || fail "apt-get update failed"
  apt-get install --yes curl ca-certificates "${debian_packages[@]}" \
    || fail "installing Debian's packages failed"

  local download_dir
  download_dir=$(mktemp -d)
  download_verified "$hangover_url" "$hangover_sha256" \
    "$download_dir/$hangover_archive"
  tar --extract --file "$download_dir/$hangover_archive" \
    --directory "$download_dir" \
    || fail "unpacking $hangover_archive failed"
  # apt installs local packages when given their paths.
  apt-get install --yes "$download_dir"/hangover*.deb \
    || fail "installing Hangover's packages failed"
  rm -r "$download_dir"
  # Drop apt's copies of the downloaded packages, which only take disk space.
  apt-get clean
}

# Unpack AutoHotkey into `autohotkey_dir`, unless it's already there.
install_autohotkey() {
  if [ -f "$autohotkey_dir/AutoHotkey32.exe" ]; then
    return
  fi
  local archive_path
  archive_path=$(mktemp)
  download_verified "$autohotkey_url" "$autohotkey_sha256" "$archive_path"
  unzip -q -o "$archive_path" -d "$autohotkey_dir" \
    || fail "unpacking AutoHotkey failed"
  rm "$archive_path"
}

# Unpack Chrome into `chrome_dir`, and install the Debian packages it needs,
# unless it's already there.
install_chrome() {
  if [ -x "$chrome_dir/chrome" ]; then
    return
  fi
  local download_dir
  download_dir=$(mktemp -d)
  download_verified "$chrome_url" "$chrome_sha256" "$download_dir/chrome.zip"
  # Chrome unpacks beside the download and moves into place only once whole, so
  # a failed unpack leaves no `chrome_dir` for the next boot to skip.
  unzip -q "$download_dir/chrome.zip" -d "$download_dir" \
    || fail "unpacking Chrome failed"
  mv "$download_dir/chrome-linux-arm64" "$chrome_dir" \
    || fail "moving Chrome into $chrome_dir failed"
  rm -r "$download_dir"

  # `deb.deps` lists the packages Chrome needs, one per line, written as in a
  # package's own dependency list. `apt-get satisfy` takes them joined by
  # commas, and finds whichever package provides each on this Debian release.
  local dependencies
  dependencies=$(paste -sd, "$chrome_dir/deb.deps")
  export DEBIAN_FRONTEND=noninteractive
  apt-get satisfy --yes --no-install-recommends "$dependencies" \
    || fail "installing Chrome's packages failed"
  apt-get clean
}

# Run the services the jobs rely on, so they're up whenever the machine is:
#
# - a virtual display for each job, so one job's windows can't take keyboard
#   focus from the other's: SuitPlay draws on `:1`, Chrome on `:2`;
# - the idle check.
start_services() {
  systemctl daemon-reload || fail "reloading systemd failed"
  systemctl enable --now xvfb@1.service xvfb@2.service \
    || fail "starting the displays failed"
  systemctl enable --now idle-poweroff.timer \
    || fail "starting the idle check failed"
}

install_packages
install_autohotkey
install_chrome
start_services
