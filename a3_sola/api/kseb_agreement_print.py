# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The KSEB Solar Agreement: KSEB's agreement for connecting the solar plant to its
distribution system, with its schedule, as the team's own KSEB Agreement.docx lays it out -
page 1 left blank at the top for the stamp paper's printed head, the agreement (api/agreement's
preamble and sixteen clauses), the parties' and witnesses' signatures, then on its own page the
schedule: (I) the consumer, (II) the premises and the plant, (III) the premises the excess
energy is wheeled to.

The answers are the job's Solar Agreement's (executed, else the latest draft), its blanks
filled from the job as the agreement fills them (agreement.pull_sources); a job with no
agreement yet prints from the job alone, with dotted lines where the agreement is still to say
- the date, the KSEB officer, the SPIN. The plant's capacity is its panels' kWp, as on Forms 2
and 3, unless the agreement was given another by hand. Rendered for the Form 3 Submission
task (KFORMS) and its pack; nothing is saved.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from a3_sola.api import agreement as agreement_api
from a3_sola.api import documents
from a3_sola.api.form2_print import _kwp

CODE = "KSEB-NETMETER-AGREEMENT"
TITLE = "KSEB Solar Agreement"


def url(installation, download=False):
	return "/api/method/a3_sola.api.kseb_agreement_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View KSEB Solar Agreement"), "url": url(installation)},
		{"label": _("Download KSEB Solar Agreement"), "url": url(installation, download=True)}]


def _agreement(inst, name=None):
	"""The job's agreement, in memory only: `name`, else the executed one, else the latest
	draft, else a new one - its blanks filled from the job either way."""
	name = name or frappe.db.get_value("Solar Agreement",
		{"solar_installation": inst.name, "docstatus": 1, "is_terminated": 0}, "name") or frappe.db.get_value(
		"Solar Agreement", {"solar_installation": inst.name, "docstatus": 0}, "name", order_by="creation desc")
	if name:
		doc = frappe.get_doc("Solar Agreement", name)
	else:
		doc = frappe.new_doc("Solar Agreement")
		doc.solar_installation = inst.name
	agreement_api.pull_sources(doc)
	# The panels' kWp, as Forms 2 and 3 say - unless someone gave the agreement another.
	if not doc.plant_capacity_kwp or flt(doc.plant_capacity_kwp) == flt(inst.get("capacity_kw")):
		doc.plant_capacity_kwp = _kwp(inst) or doc.plant_capacity_kwp
	return doc


def _plain(value):
	"""A value the agreement's wording sets in bold that the Word file does not."""
	return f'<span class="plain">{value}</span>'


def _body(doc):
	"""The agreement's own wording (api/agreement), set as the Word file sets it: the title in
	bold, underlined; in bold only the consumer's name and the capacity - not the licensee,
	the SPIN or the attestation's names."""
	values = agreement_api.build_context(doc)
	preamble = dict(values, licensee=_plain(values["licensee"]), spin=_plain(values["spin"]))
	attestation = dict(values, consumer_name=_plain(values["consumer_name"]),
		representative=_plain(values["representative"]))
	clauses = "\n".join(f"<li>{clause.format(**values)}</li>" for clause in agreement_api.CLAUSES)
	return "\n".join([f'<p class="title">{agreement_api.TITLE}</p>', agreement_api.PREAMBLE.format(**preamble),
		f"<ol>\n{clauses}\n</ol>", agreement_api.ATTESTATION.format(**attestation)])


def context(inst, name=None):
	"""(the agreement, its body as HTML) for the job `inst`."""
	doc = _agreement(inst, name)
	# Wording edited by hand on an agreement is the agreement; otherwise it is generated
	# afresh, so the capacity and anything filled in since are current.
	edited = doc.get("agreement_text") and not doc.is_new() and cint(doc.get("is_edited"))
	body = doc.agreement_text if edited else _body(doc)
	return doc, body


def file_name(inst):
	return "{0} - {1}.pdf".format(TITLE, inst.consumer_name or inst.name)


def render(inst, name=None):
	"""(file name, PDF) of the agreement for the job `inst` - the caller has checked access.
	`name`: the Solar Agreement to print, else the job's."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	doc, body = context(inst, name)
	html = frappe.render_template("a3_sola/templates/print/kseb_agreement.html", {"doc": doc, "body": body,
		"blank": agreement_api.BLANK})
	return file_name(inst), documents.plain_pdf(html, margins="18mm")


@frappe.whitelist()
def pdf(installation, download=0):
	"""The agreement, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
