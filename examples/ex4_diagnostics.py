# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT
"""Print a one-page health report from the I2C microSD Expansion module."""

import qwiic_sd_expansion_py

microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()

if not microSDexp.begin():
    print("Module not found - showing partial diagnostics anyway")

print(microSDexp.diagnostics())
