# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for tinyhtml5: only the surface this repo calls. See the
# README two levels up before extending.

from xml.etree.ElementTree import Element

def parse(document: str, namespace_html_elements: bool = ...) -> Element: ...
