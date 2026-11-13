#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Sets up the machine:
#
# - Hangover, which runs Windows programs on ARM Linux by translating their
#   Intel code;
# - AutoHotkey, a Windows program that drives SuitPlay's window;
# - Chrome for Testing, the browser the ACBL fetch drives, kept at its stable
#   release;
# - a virtual display for each job's windows;
# - the idle check, which powers the machine off once nothing needs it.
#
# Lima runs this as root on every boot, so each step skips work already done. By
# then Lima has written the files `lima.yaml` names, among them the units
# `start_services` enables.

# Hangover and AutoHotkey are pinned, each to a version and its digest, as
# `README.md` explains.
hangover_version=11.16
hangover_archive="hangover_${hangover_version}_debian13_trixie_arm64.tar"
hangover_url="https://github.com/AndreRH/hangover/releases/download/hangover-${hangover_version}/${hangover_archive}"
hangover_sha256=b5493f5903ab3c05f78bf4c03b06ac0005eb26f732437748c1592fefa45e861a

autohotkey_version=2.0.30
autohotkey_url="https://github.com/AutoHotkey/AutoHotkey/releases/download/v${autohotkey_version}/AutoHotkey_${autohotkey_version}.zip"
autohotkey_sha256=1e0ece7ecb2d5646e55758150472677996a57f9db5c83d2996d8b47b9e2f31a4
autohotkey_dir=/opt/autohotkey

# Chrome follows its stable release instead, which Chrome for Testing lists.
chrome_versions_url=https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json
# Reads that list on standard input, and prints the stable release's version and
# its download for this machine, separated by a space.
chrome_release_script='
import json, sys
stable = json.load(sys.stdin)["channels"]["Stable"]
downloads = stable["downloads"]["chrome"]
url = next(item["url"] for item in downloads if item["platform"] == "linux-arm64")
print(stable["version"], url)
'
# The ACBL fetch launches `chrome` from here.
chrome_dir=/opt/chrome-linux-arm64
# The version of the Chrome in `chrome_dir`.
chrome_version_file=$chrome_dir/version

# Virtual displays, screenshots of them for debugging, a tool to unpack
# AutoHotkey's and Chrome's archives, and Python, to read Chrome's list of
# releases.
debian_packages=(xvfb scrot unzip python3)

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

# Report a failed Chrome install or update. The machine keeps a Chrome it
# already has, so a boot without network still succeeds; with none, stop.
chrome_failed() {
  if [ -x "$chrome_dir/chrome" ]; then
    echo "setup.sh: $1; keeping the installed Chrome" >&2
  else
    fail "$1"
  fi
}

# Download Chrome `$1` from `$2` into the directory `$3`, unpack it there, and
# install the Debian packages it needs. Prints why, and fails, if a step fails.
stage_chrome() {
  local version=$1
  local url=$2
  local download_dir=$3
  curl --fail --silent --show-error --location \
    --output "$download_dir/chrome.zip" "$url" \
    || return 1
  unzip -q "$download_dir/chrome.zip" -d "$download_dir" \
    || return 1
  echo "$version" > "$download_dir/chrome-linux-arm64/version"

  # `deb.deps` lists the packages Chrome needs, one per line, written as in a
  # package's own dependency list. `apt-get satisfy` takes them joined by
  # commas, and finds whichever package provides each on this Debian release.
  # The lock timeout waits out Debian's own automatic updates.
  local dependencies
  dependencies=$(paste -sd, "$download_dir/chrome-linux-arm64/deb.deps")
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o DPkg::Lock::Timeout=300 update \
    && apt-get -o DPkg::Lock::Timeout=300 satisfy --yes \
      --no-install-recommends "$dependencies"
}

# Install Chrome's current stable release into `chrome_dir`, unless it's already
# there.
install_chrome() {
  local versions release version url download_dir
  versions=$(curl --fail --silent --show-error --location \
    "$chrome_versions_url")
  if [ -z "$versions" ]; then
    chrome_failed "looking up Chrome's stable release failed"
    return
  fi
  # `<<<` feeds the string to the script's standard input.
  release=$(python3 -c "$chrome_release_script" <<< "$versions")
  if [ -z "$release" ]; then
    chrome_failed "reading Chrome's stable release failed"
    return
  fi
  read -r version url <<< "$release"
  if [ "$(cat "$chrome_version_file" 2> /dev/null)" = "$version" ]; then
    return
  fi

  # `/var/tmp` is on the same disk as `/opt`, so moving the staged Chrome into
  # place renames it rather than copying it.
  download_dir=$(mktemp -d --tmpdir=/var/tmp)
  if ! stage_chrome "$version" "$url" "$download_dir"; then
    rm -rf "$download_dir"
    chrome_failed "installing Chrome $version failed"
    return
  fi
  rm -rf "$chrome_dir"
  mv "$download_dir/chrome-linux-arm64" "$chrome_dir" \
    || fail "moving Chrome $version into $chrome_dir failed"
  rm -rf "$download_dir"
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
