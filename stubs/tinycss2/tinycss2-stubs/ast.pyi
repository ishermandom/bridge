# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

# Minimal stubs for tinycss2.ast: only the node types this repo checks for, and
# the attributes it reads from them.

class Node:
  # The node's kind as tinycss2 names it, such as `qualified-rule` or `string`.
  type: str

class ParseError(Node):
  message: str

class QualifiedRule(Node):
  prelude: list[Node]
  content: list[Node]

class Declaration(Node):
  lower_name: str
  value: list[Node]

class StringToken(Node):
  value: str

class DimensionToken(Node):
  value: float
  lower_unit: str
