# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Phase 7: subscription lifecycle and access control.

The governing rule of this package, which every module in it obeys:

    **Suspension is never a side effect.**

An access change is always a deliberate, logged, individually reversible transition
produced by a named policy, carrying a reason a human can read. Nothing here changes
access as a consequence of doing something else, and nothing here changes access without
writing a Subscription Event first.
"""
