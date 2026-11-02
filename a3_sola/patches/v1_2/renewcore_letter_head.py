# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Renewcore's own letter pad - the header and footer artwork of its proposals
(RENC/PROP/26-27/089_R1), shipped in public/images/letterhead - as the "Renewcore Innovations
LLP" Letter Head, and the company's default where it has none or still has RIM's. Every
inner page of the proposal, the quotation and the estimate prints on it (print_frame.html,
documents.letterhead_pdf).

A Letter Head of that name already set up is kept as it is, and so is a default letter head
the company was given that is neither empty nor RIM's."""

import frappe

COMPANY = "Renewcore Innovations LLP"
LETTER_HEAD = "Renewcore Innovations LLP"
#: The letterhead first set up for the company: RIM Projects', its partner firm.
RIM = "RIM Projects Pvt. Ltd."
#: Letter Head field: (file name on the site, file shipped with the app)
IMAGES = {"image": ("renewcore_letterhead_header.jpg", "renewcore-header.jpg"),
	"footer_image": ("renewcore_letterhead_footer.jpg", "renewcore-footer.jpg")}


def execute():
	if not frappe.db.exists("Company", COMPANY):
		return
	if not frappe.db.exists("Letter Head", LETTER_HEAD):
		files = {field: _public_file(file_name, shipped) for field, (file_name, shipped) in IMAGES.items()}
		doc = frappe.new_doc("Letter Head")
		doc.letter_head_name = LETTER_HEAD
		doc.source = "Image"
		doc.footer_source = "Image"
		for field, file in files.items():
			doc.set(field, file.file_url)
		doc.insert(ignore_permissions=True)
		for file in files.values():
			frappe.db.set_value("File", file.name, {"attached_to_doctype": "Letter Head", "attached_to_name": doc.name})
	if (frappe.db.get_value("Company", COMPANY, "default_letter_head") or RIM) == RIM:
		frappe.db.set_value("Company", COMPANY, "default_letter_head", LETTER_HEAD)
	frappe.db.commit()


def _public_file(file_name, shipped):
	"""A public File of the shipped image, as an uploaded letterhead is, so the prints read it
	the same way (documents.image_src). Its URL is the one the File was given."""
	with open(frappe.get_app_path("a3_sola", "public", "images", "letterhead", shipped), "rb") as f:
		content = f.read()
	return frappe.get_doc({"doctype": "File", "file_name": file_name, "is_private": 0, "content": content}).insert(
		ignore_permissions=True)
