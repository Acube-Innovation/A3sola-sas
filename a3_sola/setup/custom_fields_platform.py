# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Platform custom fields: the tenant stamp.

Two fields, both read-only, both doing the same job from opposite ends. A Company knows
which tenant it belongs to, and a User knows which tenant they belong to - so any record's
company resolves to a tenant in one hop, and the seat-quota hook is an O(1) lookup rather
than a join through User Permission.

Read-only in the desk on purpose. Editing either of these by hand is how a user ends up
counted against one tenant's quota while holding another tenant's User Permission.
"""

PLATFORM_CUSTOM_FIELDS = {
	"Company": [
		{
			"fieldname": "a3_sola_tenant",
			"label": "Tenant",
			"fieldtype": "Link",
			"options": "Tenant",
			"read_only": 1,
			"insert_after": "company_name",
			"no_copy": 1,
			"description": "The provisioned tenant this company belongs to. Set by provisioning.",
		}
	],
	"User": [
		{
			"fieldname": "a3_sola_tenant",
			"label": "Tenant",
			"fieldtype": "Link",
			"options": "Tenant",
			"read_only": 1,
			"insert_after": "user_type",
			"no_copy": 1,
			"description": (
				"The tenant this user belongs to. Empty means internal staff, who are not "
				"metered against any seat quota."
			),
		}
	],
}
