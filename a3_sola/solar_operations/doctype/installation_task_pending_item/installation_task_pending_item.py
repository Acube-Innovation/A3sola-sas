# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One item a supplier could not give: moved off a procurement task's list while it is
awaited, and back onto it when it is received (api/purchase_list)."""

from frappe.model.document import Document


class InstallationTaskPendingItem(Document):
	pass
