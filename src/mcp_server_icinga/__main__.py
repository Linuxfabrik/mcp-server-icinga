# SPDX-License-Identifier: Unlicense

"""Allows `python -m mcp_server_icinga` as an alternative to the console script."""

import sys

from mcp_server_icinga.server import main

sys.exit(main())
