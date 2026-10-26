# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Net Metering Agreement between the eligible consumer and KSEB, as the PM Surya Ghar
portal issues it (NET.pdf): made at the consumer's premises on the day it is printed, between
the consumer - name, premises, consumer number - and KSEB, for the plant's kW; the eleven
clauses as the portal words them.

Printed in the Accept Customer task of a financed job (ACPT) as the portal prints it: Helvetica
(Liberation Sans, bundled), the filled-in details underlined. Nothing is saved; the signed copy
is uploaded to the task's row.
"""

import base64
import functools
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _row1
from a3_sola.api.form2_print import _kwp

CODE = "NET-METERING-AGREEMENT"
TITLE = "Net Metering Agreement"


def url(installation, download=False):
	return "/api/method/a3_sola.api.net_metering_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Net Metering Agreement"), "url": url(installation)},
		{"label": _("Download Net Metering Agreement"), "url": url(installation, download=True)}]


def context(inst):
	"""The agreement's blanks for the job `inst`: made at the premises, today; the plant's kW
	is the capacity applied for, else its panels' kWp."""
	row1 = _row1(inst, _consumer(inst))
	date = getdate(today())
	kw = flt(inst.get("capacity_kw")) or _kwp(inst)
	return frappe._dict({
		"place": row1["address"] or "",
		"day": date.strftime("%d"),
		"month": date.strftime("%B"),
		"year": date.strftime("%Y"),
		"name": row1["name"] or "",
		"address": row1["address"] or "",
		"consumer_number": row1["number"] or "",
		"capacity": "{0:g}".format(kw) if kw else "",
	})


@functools.lru_cache(maxsize=1)
def fonts():
	"""@font-face rules for "Agreement Sans": Liberation Sans, metric-compatible with the
	portal's Helvetica (public/fonts/liberation-sans, SIL OFL) - embedded, as neither this server
	nor the PDF renderer can be relied on to have Helvetica."""
	folder = frappe.get_app_path("a3_sola", "public", "fonts", "liberation-sans")
	rules = []
	for weight, name in (("normal", "LiberationSans-Regular.ttf"), ("bold", "LiberationSans-Bold.ttf")):
		with open(os.path.join(folder, name), "rb") as f:
			data = base64.b64encode(f.read()).decode()
		# No format() hint: the renderer's CSS parser rejects it, and the font loads without.
		rules.append('@font-face { font-family: "Agreement Sans"; font-weight: %s; '
			"src: url(data:application/x-font-ttf;base64,%s); }" % (weight, data))
	return "\n".join(rules)


def file_name(inst):
	return "{0} - {1}.pdf".format(TITLE, inst.consumer_name or inst.name)


def render(inst):
	"""(file name, PDF) of the agreement for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	# Four pages that flow, as the portal's own: a fixed letter sheet would cut it at one.
	return file_name(inst), documents.plain_pdf(html(inst), margins="20mm")


def html(inst):
	return frappe.render_template("a3_sola/templates/print/net_metering_agreement.html", {"f": context(inst),
		"fonts": fonts()})


@frappe.whitelist()
def pdf(installation, download=0):
	"""The agreement, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
