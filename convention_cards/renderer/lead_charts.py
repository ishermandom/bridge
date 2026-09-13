# Copyright 2026 Ilya Sherman (ishermandom@)
# SPDX-License-Identifier: MIT

"""Where each lead-chart card sits on the printed card.

The lead panels print example holdings ("xx xxx xxxx xxxxx", "KQx", ...) whose
individual cards a player circles to show which card they lead. The holdings are
printed artwork, not form fields, so their geometry comes from the PDF's text
layer: each character's box below was extracted with pypdfium2's character-level
text API from the pinned base card, then verified visually with every measured
character circled.

A numeric lead value in the card JSON selects the 1-based position — counting
from the left — of the circled card within its holding.
"""

from collections.abc import Mapping

from bridgodex_key import BridgodexKey

# One printed character's box: (left, bottom, right, top) in PDF points.
type CharBox = tuple[float, float, float, float]

CHART_BOXES: Mapping[BridgodexKey, tuple[CharBox, ...]] = {
  BridgodexKey('leads_vs_nt', 'honor_interior_seq_AJTx'): (
    (194.34, 13.23, 199.10, 18.92),
    (201.08, 13.18, 204.90, 19.02),
    (207.47, 13.25, 211.84, 18.94),
    (214.02, 13.25, 217.53, 17.47),
  ),
  BridgodexKey('leads_vs_nt', 'honor_interior_seq_AQJx'): (
    (163.97, 13.12, 168.73, 18.81),
    (171.25, 12.23, 176.09, 19.10),
    (178.26, 13.17, 181.69, 18.93),
    (184.51, 13.24, 188.02, 17.46),
  ),
  BridgodexKey('leads_vs_nt', 'honor_interior_seq_KT9x'): (
    (226.48, 13.23, 230.67, 18.92),
    (232.13, 13.25, 236.76, 19.02),
    (239.02, 13.22, 242.55, 19.02),
    (245.19, 13.25, 248.70, 17.47),
  ),
  BridgodexKey('leads_vs_nt', 'honor_interior_seq_QT9x'): (
    (256.16, 12.40, 260.59, 19.15),
    (263.51, 13.25, 268.14, 19.02),
    (270.53, 13.18, 274.06, 18.98),
    (276.70, 13.22, 280.21, 17.44),
  ),
  BridgodexKey('leads_vs_nt', 'honor_leads_AKxx'): (
    (164.84, 46.24, 169.60, 51.93),
    (171.43, 46.24, 175.62, 51.93),
    (176.94, 46.24, 180.45, 50.46),
    (181.83, 46.24, 185.34, 50.46),
  ),
  BridgodexKey('leads_vs_nt', 'honor_leads_JT9x'): (
    (256.88, 35.17, 260.70, 41.01),
    (263.78, 35.20, 268.15, 40.89),
    (270.53, 35.17, 274.06, 40.97),
    (276.70, 35.20, 280.21, 39.42),
  ),
  BridgodexKey('leads_vs_nt', 'honor_leads_KQJx'): (
    (165.23, 35.24, 169.87, 41.01),
    (172.14, 34.26, 176.57, 41.01),
    (179.30, 35.17, 182.73, 40.93),
    (185.55, 35.24, 189.06, 39.46),
  ),
  BridgodexKey('leads_vs_nt', 'honor_leads_KQT9'): (
    (194.92, 34.96, 199.10, 40.65),
    (200.92, 34.23, 205.76, 41.09),
    (207.44, 35.07, 211.82, 40.76),
    (214.19, 35.04, 217.72, 40.84),
  ),
  BridgodexKey('leads_vs_nt', 'honor_leads_QJTx'): (
    (226.05, 34.23, 230.89, 41.09),
    (233.40, 35.00, 236.83, 40.76),
    (239.51, 35.07, 243.88, 40.76),
    (246.06, 35.07, 249.57, 39.29),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_Hxx'): (
    (166.25, 80.11, 170.47, 85.80),
    (173.32, 80.11, 176.83, 84.33),
    (179.15, 80.11, 182.66, 84.33),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_Hxxx'): (
    (196.27, 79.99, 200.48, 85.68),
    (203.33, 79.99, 206.84, 84.21),
    (209.16, 79.99, 212.68, 84.21),
    (215.00, 79.99, 218.51, 84.21),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_Hxxxx'): (
    (230.79, 79.99, 235.00, 85.68),
    (237.85, 79.99, 241.36, 84.21),
    (243.68, 79.99, 247.20, 84.21),
    (249.52, 79.99, 253.03, 84.21),
    (255.36, 79.99, 258.87, 84.21),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_xx'): (
    (166.45, 89.56, 169.96, 93.79),
    (172.28, 89.56, 175.79, 93.79),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_xxx'): (
    (188.53, 89.39, 192.04, 93.62),
    (194.36, 89.39, 197.87, 93.62),
    (200.19, 89.39, 203.70, 93.62),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_xxxx'): (
    (215.22, 89.23, 218.73, 93.45),
    (221.05, 89.23, 224.57, 93.45),
    (226.89, 89.23, 230.40, 93.45),
    (232.72, 89.23, 236.23, 93.45),
  ),
  BridgodexKey('leads_vs_nt', 'length_leads_xxxxx'): (
    (247.70, 89.23, 251.21, 93.45),
    (253.52, 89.23, 257.04, 93.45),
    (259.36, 89.23, 262.87, 93.45),
    (265.19, 89.23, 268.70, 93.45),
    (271.02, 89.23, 274.53, 93.45),
  ),
  BridgodexKey('leads_vs_suits', 'honor_interior_seq_KJTx'): (
    (22.26, 13.34, 26.44, 19.03),
    (28.22, 13.17, 32.04, 19.02),
    (35.18, 13.20, 39.55, 18.89),
    (41.72, 13.20, 45.23, 17.42),
  ),
  BridgodexKey('leads_vs_suits', 'honor_interior_seq_KT9x'): (
    (54.52, 13.43, 58.71, 19.12),
    (60.22, 13.24, 64.85, 19.02),
    (66.85, 13.20, 70.38, 19.00),
    (73.02, 13.23, 76.53, 17.46),
  ),
  BridgodexKey('leads_vs_suits', 'honor_interior_seq_QT9x'): (
    (84.20, 12.57, 88.63, 19.32),
    (90.59, 13.24, 95.22, 19.02),
    (97.31, 13.20, 100.84, 19.00),
    (103.48, 13.23, 106.99, 17.46),
  ),
  BridgodexKey('leads_vs_suits', 'honor_leads_AKx'): (
    (21.93, 46.24, 26.69, 51.93),
    (28.52, 46.24, 32.70, 51.93),
    (34.02, 46.24, 37.53, 50.46),
  ),
  BridgodexKey('leads_vs_suits', 'honor_leads_JTx'): (
    (83.96, 35.17, 87.78, 41.01),
    (90.34, 35.24, 94.71, 40.93),
    (96.89, 35.24, 100.40, 39.46),
  ),
  BridgodexKey('leads_vs_suits', 'honor_leads_KQx'): (
    (22.32, 35.24, 26.96, 41.01),
    (29.38, 34.26, 33.81, 41.01),
    (36.44, 35.24, 39.95, 39.46),
  ),
  BridgodexKey('leads_vs_suits', 'honor_leads_QJx'): (
    (54.13, 34.23, 58.97, 41.09),
    (61.51, 34.89, 64.95, 40.65),
    (67.76, 34.96, 71.27, 39.18),
  ),
  BridgodexKey('leads_vs_suits', 'honor_leads_T9x'): (
    (112.97, 35.24, 117.60, 41.01),
    (119.94, 35.17, 123.47, 40.97),
    (126.11, 35.20, 129.62, 39.42),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_Hxx'): (
    (22.80, 80.17, 27.02, 85.86),
    (29.86, 80.17, 33.38, 84.40),
    (35.70, 80.17, 39.21, 84.40),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_Hxxx'): (
    (52.82, 80.05, 57.03, 85.74),
    (59.88, 80.05, 63.39, 84.28),
    (65.71, 80.05, 69.22, 84.28),
    (71.54, 80.05, 75.06, 84.28),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_Hxxxx'): (
    (87.33, 80.05, 91.54, 85.74),
    (94.39, 80.05, 97.90, 84.28),
    (100.22, 80.05, 103.73, 84.28),
    (106.05, 80.05, 109.57, 84.28),
    (111.89, 80.05, 115.40, 84.28),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_xx'): (
    (23.11, 89.90, 26.62, 94.12),
    (28.94, 89.90, 32.45, 94.12),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_xxx'): (
    (42.86, 90.07, 46.38, 94.29),
    (48.70, 90.07, 52.21, 94.29),
    (54.53, 90.07, 58.04, 94.29),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_xxxx'): (
    (69.56, 89.90, 73.07, 94.13),
    (75.39, 89.90, 78.90, 94.13),
    (81.22, 89.90, 84.74, 94.13),
    (87.06, 89.90, 90.57, 94.13),
  ),
  BridgodexKey('leads_vs_suits', 'length_leads_xxxxx'): (
    (102.05, 89.90, 105.56, 94.12),
    (107.88, 89.90, 111.39, 94.12),
    (113.71, 89.90, 117.22, 94.12),
    (119.54, 89.90, 123.06, 94.12),
    (125.38, 89.90, 128.89, 94.12),
  ),
}
