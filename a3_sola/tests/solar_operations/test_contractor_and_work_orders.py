# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Contractors, and work orders that are done by them or by employees and proved by
photographs that know where they were taken."""

import io

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_sola.api import photos
from a3_sola.tests.fixtures import default_company
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import make_work_order, task_row


def make_contractor(company=None, **kwargs):
	values = {
		"doctype": "Solar Contractor",
		"contractor_name": "Sparks & Co " + frappe.generate_hash(length=4),
		"contractor_type": "Electrical",
		"email_id": "sparks@example.com",
		"company": company or default_company(),
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert(ignore_permissions=True)


def jpeg_bytes(with_gps=True):
	"""A tiny JPEG, with or without GPS EXIF, made in memory."""
	from PIL import Image

	image = Image.new("RGB", (32, 32), (200, 120, 40))
	exif = Image.Exif()
	if with_gps:
		gps = exif.get_ifd(0x8825)
		gps[1] = "N"
		gps[2] = (10.0, 5.0, 30.0)
		gps[3] = "E"
		gps[4] = (76.0, 20.0, 15.0)
	buffer = io.BytesIO()
	image.save(buffer, format="JPEG", exif=exif.tobytes())
	return buffer.getvalue()


def upload(doc, content, filename):
	return frappe.get_doc(
		{"doctype": "File", "file_name": filename, "attached_to_doctype": doc.doctype,
		 "attached_to_name": doc.name, "is_private": 1, "content": content}
	).insert(ignore_permissions=True)


class TestSolarContractor(FrappeTestCase):
	def test_unique_per_company(self):
		make_contractor(contractor_name="Kerala Electricals")
		with self.assertRaises(frappe.ValidationError):
			make_contractor(contractor_name="Kerala Electricals")

	def test_a_bad_email_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_contractor(email_id="not-an-email")


class TestCrewParties(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_an_employee_row_still_fills_technician(self):
		employee = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name", limit=1)
		if not employee:
			self.skipTest("no active employee on this site")
		order = make_work_order(
			self.installation, "Module Mounting",
			crew=[{"party_type": "Employee", "party": employee[0], "role": "Electrician", "planned_hours": 4}],
		)
		self.assertEqual(order.crew[0].technician, employee[0])

	def test_a_contractor_row_names_the_contractor_and_clears_technician(self):
		contractor = make_contractor(company=self.installation.company)
		order = make_work_order(
			self.installation, "Structure Erection",
			crew=[{"party_type": "Solar Contractor", "party": contractor.name, "role": "Structural Fitter"}],
		)
		self.assertEqual(order.crew[0].party_name, contractor.contractor_name)
		self.assertFalse(order.crew[0].technician)

	def test_a_contractor_from_another_company_is_refused(self):
		other = frappe.get_all("Company", filters={"name": ["!=", self.installation.company]}, pluck="name", limit=1)
		if not other:
			self.skipTest("single-company site")
		contractor = make_contractor(company=other[0])
		with self.assertRaises(frappe.ValidationError):
			make_work_order(
				self.installation, "Structure Erection",
				crew=[{"party_type": "Solar Contractor", "party": contractor.name, "role": "Structural Fitter"}],
			)


class TestWorkOrderKinds(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_the_primary_type_follows_the_first_work_type_row(self):
		order = make_work_order(
			self.installation, None,
			work_types=[{"work_type": "DC Wiring"}, {"work_type": "AC Wiring & Earthing"}],
		)
		self.assertEqual(order.work_order_type, "DC Wiring")

	def test_the_kind_decides_the_task(self):
		make_work_order(self.installation, "Module Mounting", work_order_kind="Structure")
		row, _doc = task_row(self.installation, "IWOS")
		self.assertEqual(row.status, "In Progress")

	def test_rectification_carries_no_task(self):
		make_work_order(self.installation, "Rectification", work_order_kind="Rectification")
		for code in ("IWOS", "IWOI"):
			row, _doc = task_row(self.installation, code)
			self.assertEqual(row.status, "Pending", code)

	def test_an_installation_order_needs_located_photographs_to_submit(self):
		order = make_work_order(self.installation, "Module Mounting", work_order_kind="Installation",
		                        status="Completed")
		with self.assertRaises(frappe.ValidationError) as ctx:
			order.submit()
		self.assertIn("geo-tagged", str(ctx.exception))

	def test_a_structure_order_submits_without_them(self):
		order = make_work_order(self.installation, "Structure Erection", work_order_kind="Structure",
		                        status="Completed")
		order.submit()
		row, _doc = task_row(self.installation, "IWOS")
		self.assertEqual(row.status, "Completed")

	def test_located_photographs_are_counted_and_mapped(self):
		order = make_work_order(
			self.installation, "Module Mounting", work_order_kind="Installation",
			photos=[
				{"image": "/files/a.jpg", "latitude": 10.09, "longitude": 76.34},
				{"image": "/files/b.jpg", "latitude": 10.09, "longitude": 76.34},
				{"image": "/files/c.jpg"},
			],
		)
		self.assertEqual(order.geo_photo_count, 2)
		self.assertIn("maps.google.com/?q=10.09", order.photos[0].map_link)
		self.assertEqual(order.photos[0].geo_source, "Manual")
		self.assertFalse(order.photos[2].map_link)


class TestPhotos(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		self.order = make_work_order(self.installation, "Module Mounting", work_order_kind="Installation")

	def test_exif_coordinates_are_read_and_a_stripped_file_yields_none(self):
		# Frappe strips EXIF from every uploaded JPEG while System Settings says so (the
		# default), which is why browser capture is the primary source and EXIF the fallback.
		# The fallback is tested on a site that keeps metadata.
		frappe.get_system_settings("strip_exif_metadata_from_uploaded_images")  # loads the cached doc
		settings = frappe.local.system_settings
		kept = settings.get("strip_exif_metadata_from_uploaded_images")
		settings.strip_exif_metadata_from_uploaded_images = 0
		self.addCleanup(setattr, settings, "strip_exif_metadata_from_uploaded_images", kept)
		tagged = upload(self.order, jpeg_bytes(True), "tagged.jpg")
		plain = upload(self.order, jpeg_bytes(False), "plain.jpg")
		found = photos.read_exif_gps(tagged.file_url)
		self.assertAlmostEqual(found["latitude"], 10.091667, places=4)
		self.assertAlmostEqual(found["longitude"], 76.3375, places=4)
		self.assertIsNone(photos.read_exif_gps(plain.file_url))

	def test_the_collage_is_a_pdf_of_the_located_photographs(self):
		files = [upload(self.order, jpeg_bytes(False), f"site{i}.jpg") for i in range(3)]
		self.order.set(
			"photos",
			[{"image": f.file_url, "latitude": 10.09, "longitude": 76.34, "caption": f"Photo {i}"} for i, f in enumerate(files)]
			+ [{"image": files[0].file_url}],
		)
		self.order.save(ignore_permissions=True)
		pdf = photos.build_collage_pdf(self.installation.name)
		self.assertTrue(pdf.startswith(b"%PDF"))
		self.assertEqual(len(photos.site_photos(self.installation.name)), 3)

	def test_a_job_without_located_photographs_has_no_collage(self):
		with self.assertRaises(frappe.ValidationError):
			photos.build_collage_pdf(self.installation.name)
