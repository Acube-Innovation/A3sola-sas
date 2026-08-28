# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a new tenant gets, resolved from data rather than from a script.

A blueprint is the difference between a product and a pile of provisioning scripts: when
the client decides every new tenant should get one more document template, that is a row
somebody adds in the desk, not a deploy.

The one thing worth being careful about is the payload. Blueprint payloads are written by
trusted administrators, so this is not primarily a defence against them - it is a defence
against the day somebody wires blueprint editing into a customer-facing screen and nobody
remembers that the payload used to be evaluated. `render_payload` therefore substitutes a
fixed allowlist of tokens by plain string replacement. No Jinja, no eval, no attribute
access, no reach into Python objects. A token that is not on the list is left alone rather
than resolved, so a typo produces a visible `{{whatever}}` in the seeded record instead of
silently pulling in something it should not.
"""

import json

import frappe
from frappe import _

#: Every token a payload may use. Deliberately small.
ALLOWED_TOKENS = (
	"tenant_code",
	"tenant_name",
	"company",
	"company_abbr",
	"state",
	"state_code",
	"country",
	"currency",
	"admin_email",
	"tenant",
)


def resolve_blueprint(plan=None):
	"""The blueprint for a plan: its own, else the default, else the only active one.

	Returns None when no blueprint is configured at all. That is not an error - a site
	that has not defined one still provisions, it simply seeds nothing beyond what the
	structural steps create, and the job records that it found no blueprint.
	"""
	if plan:
		specific = frappe.db.get_value(
			"Tenant Blueprint", {"applicable_plan": plan, "is_active": 1}, "name"
		)
		if specific:
			return specific
	default = frappe.db.get_value(
		"Tenant Blueprint", {"is_default": 1, "is_active": 1, "applicable_plan": ""}, "name"
	)
	if default:
		return default
	default = frappe.db.get_value("Tenant Blueprint", {"is_default": 1, "is_active": 1}, "name")
	if default:
		return default
	any_active = frappe.get_all(
		"Tenant Blueprint", filters={"is_active": 1}, pluck="name", limit=1, order_by="creation asc"
	)
	return any_active[0] if any_active else None


def render_payload(payload, context):
	"""Substitute the allowlisted tokens and return the parsed JSON.

	`context` is a plain dict. Values are stringified and inserted literally; a value
	containing a brace does not start a second round of substitution, because substitution
	is a single pass over the allowlist rather than a loop until stable.
	"""
	text = payload or "{}"
	if not isinstance(text, str):
		text = json.dumps(text)
	for token in ALLOWED_TOKENS:
		if token not in context:
			continue
		value = context.get(token)
		value = "" if value is None else str(value)
		# JSON-escape so a value containing a quote cannot break out of its string.
		escaped = json.dumps(value)[1:-1]
		text = text.replace("{{" + token + "}}", escaped)
		text = text.replace("{{ " + token + " }}", escaped)
	try:
		parsed = json.loads(text)
	except ValueError as exception:
		frappe.throw(
			_("A blueprint payload is not valid JSON after substitution: {0}").format(exception),
			title=_("Bad Blueprint Payload"),
		)
	if not isinstance(parsed, dict | list):
		frappe.throw(
			_("A blueprint payload must be a JSON object or a list of objects."),
			title=_("Bad Blueprint Payload"),
		)
	return parsed


def payload_records(item, context):
	"""One blueprint item's payload as a list of record dicts."""
	if not (item.payload or "").strip():
		return []
	parsed = render_payload(item.payload, context)
	records = parsed if isinstance(parsed, list) else [parsed]
	for record in records:
		if not isinstance(record, dict):
			frappe.throw(
				_("Blueprint item {0} produced a payload entry that is not an object.").format(
					item.idx
				),
				title=_("Bad Blueprint Payload"),
			)
	return records


def mandatory_items(blueprint_name):
	if not blueprint_name:
		return []
	blueprint = frappe.get_cached_doc("Tenant Blueprint", blueprint_name)
	return [item for item in blueprint.seed_items if item.is_mandatory]
