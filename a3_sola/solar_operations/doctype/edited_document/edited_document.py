# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A job's printed paper as someone edited it on the portal (api/document_editor): the paper
prints this text in place of the generated one until it is reset."""

from frappe.model.document import Document


class EditedDocument(Document):
	pass
