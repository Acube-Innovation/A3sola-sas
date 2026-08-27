# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Shared business logic for the a3_sola app.

Every reusable calculation lives here as a whitelisted function rather than inside a
doctype controller, so later modules (Solar Operations, Solar Projects, Platform) call it
directly instead of duplicating it.

    calculations  sizing, generation, telescopic billing, savings, subsidy, cashflow
    statutory     DISCOM application / registration / net-meter fees and the refund
    regulation    dated regulatory constraints such as the three-phase threshold
    eligibility   the subsidy eligibility rule registry
    outreach      the WhatsApp/email cadence and message rendering
    naming        runtime naming-series prefixes read from A3 Sola Settings
    permissions   the shared multi-tenant permission implementation
    handoff       the Phase 2 extension point
"""
