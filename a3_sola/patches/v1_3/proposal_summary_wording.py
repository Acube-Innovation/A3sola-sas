import frappe

#: The proposal's wording, in the companies' document templates as in the code: the
#: summary's "Expected generation per day", and the plant without "Rooftop".
REPLACE = (
	("Expected generated per day", "Expected generation per day"),
	("Grid Connected Rooftop Solar Power Plant", "Grid Connected Solar Power Plant"),
)


def execute():
	"""Only these phrases change: the rest of each body is the company's own."""
	for name, body in frappe.get_all("Solar Document Template", fields=["name", "body_template"], as_list=True):
		new = body or ""
		for old, to in REPLACE:
			new = new.replace(old, to)
		if new != (body or ""):
			frappe.db.set_value("Solar Document Template", name, "body_template", new, update_modified=False)
