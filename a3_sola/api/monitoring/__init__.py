# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Phase 8: knowing when something breaks.

The second most likely production failure in this system is a scheduler silently stopping.
No error, no alert, billing just does not happen, and it is found weeks later during a
revenue review. Everything here exists to make ABSENCE detectable, because error at least
logs something.
"""
