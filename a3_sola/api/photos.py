# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Site photographs: where they were taken, and a collage of them for the bank.

Two ways a photo gets its coordinates. The browser's geolocation, asked for when a row is
added on site - the primary path, because it works on every phone that can open the desk.
And the photo's own EXIF, read when a file uploaded later still carries it - best effort,
because upload pipelines strip it as often as not.
"""

import base64
import io

import frappe
from frappe import _
from frappe.utils import cint, flt

GPS_IFD = 0x8825


@frappe.whitelist()
def read_exif_gps(file_url):
	"""Latitude and longitude from a JPEG's EXIF, or None when it carries none.

	Best effort by design: Frappe strips EXIF from uploaded JPEGs whenever System Settings
	"Strip EXIF metadata from uploaded images" is on, which it is by default. Browser
	capture at the moment the photograph is added is the primary source of coordinates.
	"""
	if not file_url:
		return None
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return None
	file_doc = frappe.get_doc("File", name)
	if file_doc.attached_to_doctype and file_doc.attached_to_name:
		file_doc.check_permission("read")
	try:
		from PIL import Image

		with Image.open(io.BytesIO(file_doc.get_content())) as image:
			exif = image.getexif()
			gps = exif.get_ifd(GPS_IFD) if exif is not None else {}
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: exif read {file_url}")
		return None
	return _decimal_coordinates(gps)


def _decimal_coordinates(gps):
	if not gps or 2 not in gps or 4 not in gps:
		return None

	def to_degrees(value):
		degrees, minutes, seconds = (flt(v) for v in value)
		return degrees + minutes / 60.0 + seconds / 3600.0

	try:
		latitude = to_degrees(gps[2])
		longitude = to_degrees(gps[4])
	except Exception:
		return None
	if str(gps.get(1, "N")).upper().startswith("S"):
		latitude = -latitude
	if str(gps.get(3, "E")).upper().startswith("W"):
		longitude = -longitude
	if not (latitude or longitude):
		return None
	return {"latitude": round(latitude, 6), "longitude": round(longitude, 6)}


def site_photos(installation, only_geotagged=True):
	"""Every site photo of a job, from its work orders, oldest first."""
	rows = frappe.db.sql(
		"""
		select p.image, p.caption, p.work_type, p.latitude, p.longitude, p.captured_on,
		       p.include_in_collage, wo.name as work_order, wo.work_order_kind
		from `tabSite Photo` p
		join `tabInstallation Work Order` wo on wo.name = p.parent
		where wo.solar_installation = %s and wo.docstatus < 2
		order by p.captured_on asc, p.idx asc
		""",
		(installation,),
		as_dict=True,
	)
	if only_geotagged:
		rows = [r for r in rows if r.latitude and r.longitude]
	return rows


def build_collage_pdf(installation, columns=None, max_photos=None, attach_to=None, title=None):
	"""A PDF grid of the job's geo-tagged photographs, each captioned with its coordinates.

	Returns the PDF bytes, or the File url when `attach_to` (doctype, name) is given.
	"""
	from frappe.utils.pdf import get_pdf

	columns = cint(columns) or cint(frappe.db.get_single_value("A3 Sola Settings", "collage_columns")) or 2
	limit = cint(max_photos) or cint(frappe.db.get_single_value("A3 Sola Settings", "collage_max_photos")) or 24
	photos = [p for p in site_photos(installation) if cint(p.include_in_collage)][:limit]
	if not photos:
		frappe.throw(_("There are no geo-tagged photographs on {0} yet.").format(installation))

	inst = frappe.db.get_value(
		"Solar Installation", installation, ["consumer_name", "capacity_kw", "installation_address"], as_dict=True
	)
	width = int(100 / columns)
	cells = []
	for photo in photos:
		data = _thumbnail_data_uri(photo.image)
		if not data:
			continue
		caption = " · ".join(
			str(bit)
			for bit in (
				f"{flt(photo.latitude, 6)}, {flt(photo.longitude, 6)}",
				frappe.utils.format_datetime(photo.captured_on, "dd MMM yyyy HH:mm") if photo.captured_on else None,
				photo.work_type,
				photo.caption,
			)
			if bit
		)
		cells.append(
			f'<div style="display:inline-block;width:{width - 2}%;margin:1%;vertical-align:top;'
			f'page-break-inside:avoid"><img src="{data}" style="width:100%;border:1px solid #999">'
			f'<div style="font-size:9px;color:#333;margin-top:3px">{frappe.utils.escape_html(caption)}</div></div>'
		)
	html = (
		f"<h3 style='font-family:sans-serif;margin:0 0 4px'>{frappe.utils.escape_html(title or _('Installation Photographs'))}</h3>"
		f"<p style='font-family:sans-serif;font-size:11px;margin:0 0 10px'>{frappe.utils.escape_html(inst.consumer_name or '')} · "
		f"{flt(inst.capacity_kw):g} kWp · {frappe.utils.escape_html(installation)} · {len(cells)} {_('photographs')}</p>"
		+ "".join(cells)
	)
	pdf = get_pdf(html)
	if not attach_to:
		return pdf
	doctype, name = attach_to
	file_name = f"PHOTO-COLLAGE-{name}.pdf"
	for existing in frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "file_name": file_name}, pluck="name"
	):
		frappe.delete_doc("File", existing, ignore_permissions=True, force=True)
	file_doc = frappe.get_doc(
		{"doctype": "File", "file_name": file_name, "attached_to_doctype": doctype, "attached_to_name": name,
		 "is_private": 1, "content": pdf}
	).insert(ignore_permissions=True)
	return file_doc.file_url


def _thumbnail_data_uri(file_url, max_side=1200):
	"""The image, downscaled and inlined - wkhtmltopdf cannot fetch private files by URL."""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return None
	try:
		from PIL import Image, ImageOps

		with Image.open(io.BytesIO(frappe.get_doc("File", name).get_content())) as image:
			image = ImageOps.exif_transpose(image).convert("RGB")
			image.thumbnail((max_side, max_side))
			buffer = io.BytesIO()
			image.save(buffer, format="JPEG", quality=80)
	except Exception:
		return None
	return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
