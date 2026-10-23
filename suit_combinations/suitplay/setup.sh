#!/usr/bin/env bash
# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT
#
# Sets up the machine that runs SuitPlay:
#
# - Hangover, which runs Windows programs on ARM Linux by translating their
#   Intel code;
# - AutoHotkey, a Windows program that drives SuitPlay's window;
# - a virtual display for both to draw on.
#
# Lima runs this as root on every boot, so each step skips work already done.

hangover_version=11.16
hangover_archive="hangover_${hangover_version}_debian13_trixie_arm64.tar"
hangover_url="https://github.com/AndreRH/hangover/releases/download/hangover-${hangover_version}/${hangover_archive}"
hangover_sha256=b5493f5903ab3c05f78bf4c03b06ac0005eb26f732437748c1592fefa45e861a

autohotkey_version=2.0.30
autohotkey_url="https://github.com/AutoHotkey/AutoHotkey/releases/download/v${autohotkey_version}/AutoHotkey_${autohotkey_version}.zip"
autohotkey_sha256=1e0ece7ecb2d5646e55758150472677996a57f9db5c83d2996d8b47b9e2f31a4
autohotkey_dir=/opt/autohotkey

# The virtual display, screenshots of it for debugging, and a tool to unpack
# AutoHotkey's archive.
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

# Run the virtual display as a service, so it's up whenever the machine is.
# Programs reach it with `DISPLAY=:1`.
start_display() {
  cat > /etc/systemd/system/xvfb.service << 'UNIT'
[Unit]
Description=Virtual display :1 for SuitPlay

[Service]
User=nobody
ExecStart=/usr/bin/Xvfb :1 -screen 0 1280x1024x24 -nolisten tcp
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload || fail "reloading systemd failed"
  systemctl enable --now xvfb.service || fail "starting the display failed"
}

install_packages
install_autohotkey
start_display
