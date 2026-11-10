# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""RIM Projects' letter pad (letterpad-Rim-PVT-LTD.pdf) - its header band, and its footer with
the large "R" watermark that the text runs over - shipped in public/images/letterhead, as the
"RIM Projects Pvt. Ltd." Letter Head. The bank's and PM Surya Ghar's documents in the registered
vendor's (RIM) format print on it (documents.RIM_TEMPLATES, rim_letter_head): the loan's and
the bank completion papers. The company's default letter head (Renewcore's) is left as it is.

A Letter Head of that name already set up is kept as it is."""

import frappe

LETTER_HEAD = "RIM Projects Pvt. Ltd."
#: Letter Head field: (file name on the site, file shipped with the app)
IMAGES = {"image": ("rim_letterhead_header.jpg", "rim-header.jpg"),
	"footer_image": ("rim_letterhead_footer.jpg", "rim-footer.jpg")}


def execute():
	if frappe.db.exists("Letter Head", LETTER_HEAD):
		return
	from a3_sola.patches.v1_2.renewcore_letter_head import _public_file

	files = {field: _public_file(file_name, shipped) for field, (file_name, shipped) in IMAGES.items()}
	doc = frappe.new_doc("Letter Head")
	doc.letter_head_name = LETTER_HEAD
	doc.source = "Image"
	doc.footer_source = "Image"
	doc.is_default = 0
	for field, file in files.items():
		doc.set(field, file.file_url)
	doc.insert(ignore_permissions=True)
	for file in files.values():
		frappe.db.set_value("File", file.name, {"attached_to_doctype": "Letter Head", "attached_to_name": doc.name})
	frappe.db.commit()
