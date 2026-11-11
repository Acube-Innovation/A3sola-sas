# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal as an editable Word file, for the Administrator to change before it goes out.

Built from the same print as the PDF (the Solar Proposal Document format), so the words,
numbers and tables are the PDF's: the print's HTML is walked page by page into a .docx -
headings, paragraphs, lists, tables and pictures become their Word equivalents, and the
frame every inner page shares (logo and website at the top, address, phone and email at the
foot) becomes the Word header and footer. The cover is the first page, without them.

What the PDF draws for its look - the blue bands, the icons - is left out: Word gets the
content in plain, editable form, not a copy of the page.
"""

import base64
import io
import os
import re

import frappe
from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

#: Only the built-in Administrator downloads the Word file (the request was "if admin is
#: logged in"); everyone else has the PDF.
WORD_USER = "Administrator"

SERIF = "Palatino Linotype"
SANS = "Calibri"
NAVY = RGBColor(0x10, 0x27, 0x5E)
TEAL = RGBColor(0x2A, 0x6F, 0x8F)
GREY = RGBColor(0x55, 0x55, 0x55)
TEXT = RGBColor(0x1F, 0x1F, 0x1F)

#: A4 with the margins the print's text column sits in.
PAGE_W, PAGE_H = Cm(21), Cm(29.7)
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = Cm(2.2), Cm(3.2), Cm(2.8)
TEXT_W = PAGE_W - 2 * MARGIN_X

#: Each table's shading as the print has it: the plant's cost sky blue, the KSEBL expenses
#: and the add-ons pale blue (print_rest.html).
TABLE_FILL = {"a3r-table--plant": "81CCFF", "a3r-table--kseb": "D0E6F6"}
HEADINGS = {"h1": 18, "h2": 14, "h3": 12, "h4": 11, "h5": 11, "h6": 11}
INLINE = {"b", "strong", "i", "em", "u", "span", "a", "small", "sup", "sub", "font", "code", "label", "mark", "s", "del"}
#: The inner pages' frame, which the Word header and footer carry instead.
FRAME = {"a3l-art", "a3l-band", "a3l-logo", "a3l-web", "a3l-foot"}
#: Alignment the print gives by class rather than by a style on the element.
CLASS_ALIGN = {
	"a3l-date": WD_ALIGN_PARAGRAPH.RIGHT,
	"a3l-opening": WD_ALIGN_PARAGRAPH.JUSTIFY,
	"a3l-intro": WD_ALIGN_PARAGRAPH.JUSTIFY,
	"a3s3-spec": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
SKIP = {"style", "script", "svg", "colgroup", "col", "head", "title", "meta", "link"}


def can_download(user=None):
	return (user or frappe.session.user) == WORD_USER


def route(name):
	from urllib.parse import quote

	return "/api/method/a3_sola.api.proposal_word.download?name=" + quote(name)


@frappe.whitelist()
def download(name):
	"""The proposal `name` as a .docx, for the Administrator only."""
	from a3_sola.api.portal_proposal import SLUG
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import proposal_print_format
	from a3_sola.www.a3solaportal.collections import load_record

	if not can_download():
		frappe.throw(frappe._("Only the Administrator can download the proposal as Word."), frappe.PermissionError)
	doc = load_record(SLUG, name, "read")
	html = frappe.get_print(doc.doctype, doc.name, print_format=proposal_print_format(), no_letterhead=0)
	frappe.local.response.filename = "{0}.docx".format(doc.get("proposal_file_name") or doc.name)
	frappe.local.response.filecontent = build(html)
	frappe.local.response.type = "download"


def build(html):
	"""The .docx bytes for a rendered proposal print."""
	soup = BeautifulSoup(html, "html.parser")
	root = soup.select_one(".print-format") or soup.body or soup
	word = Word()
	word.frame(soup.select_one(".a3l-page"))
	word.blocks(root, word.doc)
	out = io.BytesIO()
	word.doc.save(out)
	return out.getvalue()


class Sink:
	"""Where paragraphs go: the document body or a table cell (whose first paragraph exists)."""

	def __init__(self, target):
		self.target = target
		self.fresh = list(target.paragraphs) if hasattr(target, "_tc") else []

	def paragraph(self):
		return self.fresh.pop(0) if self.fresh else self.target.add_paragraph()

	def table(self, rows, cols):
		return self.target.add_table(rows=rows, cols=cols)


class Word:
	def __init__(self):
		self.doc = Document()
		section = self.doc.sections[0]
		section.page_width, section.page_height = PAGE_W, PAGE_H
		section.left_margin = section.right_margin = MARGIN_X
		section.top_margin, section.bottom_margin = MARGIN_TOP, MARGIN_BOTTOM
		section.header_distance = section.footer_distance = Cm(0.8)
		# The cover is the first page, without the header and footer.
		section.different_first_page_header_footer = True
		normal = self.doc.styles["Normal"]
		normal.font.name, normal.font.size, normal.font.color.rgb = SERIF, Pt(11), TEXT
		normal.element.rPr.rFonts.set(qn("w:eastAsia"), SERIF)
		normal.paragraph_format.space_after = Pt(6)
		normal.paragraph_format.line_spacing = 1.15
		self.started = False  # nothing written yet: a page break first would leave a blank page
		self.pending_break = False  # a page break the print asks for, written before what follows
		self.last_table = None  # (gap paragraph, classes) of the table just written
		self.lists = []  # the open lists, innermost last: {"ordered", "n", "type"}
		self.marker = None  # the list marker the next paragraph starts with

	# ------------------------------------------------------------------ the page frame
	def frame(self, page):
		"""The header and footer, from the first inner page's frame."""
		if not page:
			return
		section = self.doc.sections[0]
		header, footer = section.header, section.footer
		band = page.select_one("img.a3l-band:not(.a3l-band--bottom)")
		foot_band = page.select_one("img.a3l-band--bottom")
		head_p = header.paragraphs[0]
		if band and self.picture(head_p, band.get("src"), TEXT_W):
			pass
		else:
			logo, web = page.select_one(".a3l-logo"), page.select_one(".a3l-web")
			table = header.add_table(1, 2, TEXT_W)
			left, right = table.rows[0].cells
			if logo:
				self.picture(left.paragraphs[0], logo.get("src"), Cm(3.6))
			if web:
				p = right.paragraphs[0]
				p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
				self.run(p, web.get_text(" ", strip=True), {"color": GREY, "size": 10, "font": SANS})
			right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
			head_p._element.getparent().remove(head_p._element)
		foot_p = footer.paragraphs[0]
		if foot_band and self.picture(foot_p, foot_band.get("src"), TEXT_W):
			return
		left_el, right_el = page.select_one(".a3l-foot__left"), page.select_one(".a3l-foot__right")
		table = footer.add_table(1, 2, TEXT_W)
		left, right = table.rows[0].cells
		style = {"color": GREY, "size": 9, "font": SANS}
		if left_el:
			lines = [t.strip() for t in left_el.get_text("\n").split("\n") if t.strip()]
			p = left.paragraphs[0]
			for i, line in enumerate(lines):
				if i:
					p.add_run().add_break()
				self.run(p, line, style)
		if right_el:
			p = right.paragraphs[0]
			p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
			for i, line in enumerate(x.get_text(" ", strip=True) for x in right_el.find_all("p")):
				if i:
					p.add_run().add_break()
				self.run(p, line, style)
		foot_p._element.getparent().remove(foot_p._element)

	# ------------------------------------------------------------------ blocks
	def blocks(self, el, target, fmt=None, align=None):
		"""Write el's children into target (the body or a cell)."""
		sink = target if isinstance(target, Sink) else Sink(target)
		fmt = fmt or {}
		para = None
		for child in el.children:
			if isinstance(child, NavigableString):
				if child.__class__.__name__ in ("Comment", "Doctype", "Declaration", "ProcessingInstruction"):
					continue
				text = re.sub(r"\s+", " ", str(child))
				if not text.strip():
					if para is not None and text:
						self.run(para, " ", fmt)
					continue
				if para is None:
					para = self.new_paragraph(sink, align)
					text = text.lstrip()
				self.run(para, text, fmt)
				continue
			if not isinstance(child, Tag) or child.name in SKIP:
				continue
			name = child.name
			if name == "br":
				if para is not None:
					para.add_run().add_break()
				continue
			if name in INLINE:
				if not child.get_text(strip=True) and not child.find("img"):
					continue
				if para is None:
					para = self.new_paragraph(sink, align)
				self.inline(para, child, fmt)
				continue
			if name == "img":
				if set(child.get("class") or []) & FRAME:
					continue
				if para is None:
					para = self.new_paragraph(sink, align or WD_ALIGN_PARAGRAPH.CENTER)
				self.picture(para, child.get("src"), self.image_width(child))
				continue
			para = None
			self.block(child, sink, fmt, align)

	def block(self, el, sink, fmt, align):
		name, classes = el.name, set(el.get("class") or [])
		style = el.get("style") or ""
		if "page-break-before" in style or "break-before" in style:
			if self.started:
				self.pending_break = True
			self.blocks(el, sink, fmt, align)
			return
		if "a3l-page" in classes and self.pending_break:
			# The print starts a new sheet for every page, as its pages are fixed frames. In
			# Word text flows, so a page that only continues the last one - the rest of a
			# table, a numbered list going on - follows straight on; others start a page.
			self.pending_break = False
			if not _continues(el):
				self.page_break(sink)
		elif self.pending_break:
			self.pending_break = False
			self.page_break(sink)
		if "a3l-sign" in classes:
			self.new_paragraph(sink).paragraph_format.space_after = Pt(12)  # room to sign
		if "a3c-cover" in classes:
			self.cover(el)
			return
		if classes & FRAME:
			return  # the frame: the header and footer carry it
		if name in HEADINGS:
			p = self.new_paragraph(sink, align)
			p.paragraph_format.keep_with_next = True
			p.paragraph_format.space_before = Pt(10 if name in ("h1", "h2") else 6)
			self.inline_children(p, el, dict(fmt, bold=True, size=HEADINGS[name], color=NAVY))
			return
		if name == "p":
			p = self.new_paragraph(sink, self.alignment(el, classes) or align)
			self.inline_children(p, el, fmt)
			return
		if name in ("ul", "ol"):
			self.lists.append({
				"ordered": name == "ol",
				"n": int(el.get("start") or 1) - 1,
				"type": el.get("type") or "1",
			})
			for li in el.find_all("li", recursive=False):
				self.list_item(li, sink, fmt, align)
			self.lists.pop()
			return
		if name == "li":
			self.list_item(el, sink, fmt, align)
			return
		if name == "table":
			self.table(el, sink, fmt)
			return
		# div, section, blockquote, ... : their children, as blocks
		self.blocks(el, sink, fmt, self.alignment(el, classes) or align)

	def list_item(self, li, sink, fmt, align):
		state = self.lists[-1] if self.lists else {"ordered": False, "n": 0, "type": "1"}
		hidden = "a3a-cont" in (li.get("class") or [])  # a list item continued from the last page
		if not hidden:
			state["n"] += 1
			self.marker = self.list_marker(state)
		self.blocks(li, sink, fmt, align)
		self.marker = None

	def list_marker(self, state):
		if not state["ordered"]:
			return "•" if len(self.lists) % 2 else "◦"
		n, kind = state["n"], state["type"]
		if kind in ("a", "A"):
			letter = chr(ord("a") + (n - 1) % 26)
			return (letter.upper() if kind == "A" else letter) + "."
		if kind in ("i", "I"):
			roman = _roman(n)
			return (roman.upper() if kind == "I" else roman) + "."
		return "{0}.".format(n)

	def new_paragraph(self, sink, align=None):
		p = sink.paragraph()
		self.started = True
		if align is not None:
			p.alignment = align
		depth = len(self.lists)
		if depth:
			indent = Cm(0.75 * depth)
			p.paragraph_format.left_indent = indent
			if self.marker:
				p.paragraph_format.first_line_indent = -Cm(0.6)
				p.paragraph_format.tab_stops.add_tab_stop(indent)
				p.add_run(self.marker + "\t")
				self.marker = None
			p.paragraph_format.space_after = Pt(3)
		return p

	def page_break(self, sink):
		p = sink.paragraph()
		p.add_run().add_break(WD_BREAK.PAGE)
		p.paragraph_format.space_after = Pt(0)

	# ------------------------------------------------------------------ inline
	def inline_children(self, p, el, fmt):
		for child in el.children:
			if isinstance(child, NavigableString):
				if child.__class__.__name__ == "Comment":
					continue
				text = re.sub(r"\s+", " ", str(child))
				if not p.runs or p.text.endswith(("\t", " ")) or not p.text:
					text = text.lstrip()
				if text:
					self.run(p, text, fmt)
			elif isinstance(child, Tag) and child.name not in SKIP:
				if child.name == "br":
					p.add_run().add_break()
				elif child.name == "img":
					self.picture(p, child.get("src"), self.image_width(child))
				else:
					self.inline(p, child, fmt)

	def inline(self, p, el, fmt):
		name, f = el.name, dict(fmt)
		style = (el.get("style") or "").replace(" ", "").lower()
		if name in ("b", "strong") or "font-weight:bold" in style or "font-weight:700" in style:
			f["bold"] = True
		if name in ("i", "em") or "font-style:italic" in style:
			f["italic"] = True
		if name == "u" or "text-decoration:underline" in style:
			f["underline"] = True
		if name in ("s", "del"):
			f["strike"] = True
		if name == "sup":
			f["superscript"] = True
		if name == "sub":
			f["subscript"] = True
		self.inline_children(p, el, f)

	def run(self, p, text, fmt):
		r = p.add_run(text)
		if fmt.get("bold"):
			r.bold = True
		if fmt.get("italic"):
			r.italic = True
		if fmt.get("underline"):
			r.underline = True
		if fmt.get("strike"):
			r.font.strike = True
		if fmt.get("superscript"):
			r.font.superscript = True
		if fmt.get("subscript"):
			r.font.subscript = True
		if fmt.get("size"):
			r.font.size = Pt(fmt["size"])
		if fmt.get("color") is not None:
			r.font.color.rgb = fmt["color"]
		if fmt.get("font"):
			r.font.name = fmt["font"]
		return r

	@staticmethod
	def alignment(el, classes):
		for cls in classes:
			if cls in CLASS_ALIGN:
				return CLASS_ALIGN[cls]
		style = (el.get("style") or "").replace(" ", "").lower()
		if "c" in classes or "text-align:center" in style:
			return WD_ALIGN_PARAGRAPH.CENTER
		if "r" in classes or "text-align:right" in style:
			return WD_ALIGN_PARAGRAPH.RIGHT
		if "text-align:justify" in style:
			return WD_ALIGN_PARAGRAPH.JUSTIFY
		return None

	# ------------------------------------------------------------------ the cover
	def cover(self, el):
		"""Page 1: title, scope, customer, number and date, logo and address, centred."""
		body = el.select_one(".a3c-body") or el
		first = True
		looks = {
			"a3c-title": {"bold": True, "size": 30, "color": NAVY, "font": SANS, "upper": True, "after": 26},
			"a3c-scope": {"size": 18, "color": TEAL, "font": SANS, "upper": True, "after": 14},
			"a3c-for": {"size": 20, "color": NAVY, "font": SANS, "after": 6},
			"a3c-name": {"bold": True, "size": 22, "color": NAVY, "font": SANS, "after": 10},
			"a3c-ref": {"size": 14, "color": RGBColor(0x1F, 0x2B, 0x3D), "after": 0},
			"a3c-address": {"size": 12, "color": GREY, "after": 0},
		}
		for child in body.find_all(["h1", "p", "img"], recursive=False):
			p = self.doc.add_paragraph()
			self.started = True
			p.alignment = WD_ALIGN_PARAGRAPH.CENTER
			if first:
				p.paragraph_format.space_before = Cm(3)
				first = False
			if child.name == "img":
				p.paragraph_format.space_before = Pt(26)
				p.paragraph_format.space_after = Pt(18)
				self.picture(p, child.get("src"), Cm(5.5))
				continue
			look = next((v for k, v in looks.items() if k in (child.get("class") or [])), {})
			p.paragraph_format.space_after = Pt(look.get("after", 6))
			text = child.get_text(" ", strip=True)
			self.run(p, text.upper() if look.get("upper") else text, look)

	# ------------------------------------------------------------------ tables
	def table(self, el, sink, fmt):
		rows = [tr for tr in el.find_all("tr") if tr.find_parent("table") is el]
		if not rows:
			return
		# Lay the cells on a grid, as the browser does with rowspan and colspan.
		grid, cells = {}, []
		for r, tr in enumerate(rows):
			c = 0
			for td in tr.find_all(["td", "th"], recursive=False):
				while (r, c) in grid:
					c += 1
				rs, cs = max(int(td.get("rowspan") or 1), 1), max(int(td.get("colspan") or 1), 1)
				rs = min(rs, len(rows) - r)
				for dr in range(rs):
					for dc in range(cs):
						grid[(r + dr, c + dc)] = td
				cells.append((r, c, rs, cs, td, tr))
				c += cs
		ncols = max(c for _, c in grid) + 1
		table_classes = el.get("class") or []
		if self.last_table and self.last_table[1] == table_classes and not el.find("th"):
			# The rest of the table the print carried onto its next page: no gap between, so
			# Word joins the two into one table.
			gap = self.last_table[0]._element
			after = gap.getnext()
			if after is None or after.tag == qn("w:sectPr"):
				gap.getparent().remove(gap)
		table = sink.table(len(rows), ncols)
		self.started = True
		table.style = "Table Grid"
		table.autofit = False
		widths = self.column_widths(el, ncols)
		for row in table.rows:
			for i, cell in enumerate(row.cells):
				cell.width = widths[i]
		fill = next((v for k, v in TABLE_FILL.items() if k in table_classes), None)
		for r, c, rs, cs, td, tr in cells:
			cell = table.cell(r, c)
			if rs > 1 or cs > 1:
				cell = cell.merge(table.cell(r + rs - 1, c + cs - 1))
			cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
			classes = set(td.get("class") or [])
			f = dict(fmt)
			if td.name == "th" or "b" in (tr.get("class") or []):
				f["bold"] = True
			align = self.alignment(td, classes)
			if td.name == "th" and align is None:
				align = WD_ALIGN_PARAGRAPH.CENTER
			saved, self.lists = self.lists, []
			self.blocks(td, cell, f, align)
			self.lists = saved
			for p in cell.paragraphs:
				p.paragraph_format.space_after = Pt(2)
				if align is not None and p.alignment is None:
					p.alignment = align
			# Merging keeps every merged cell's empty paragraph: drop those after the content.
			while len(cell.paragraphs) > 1 and not cell.paragraphs[-1].text.strip() \
					and not cell.paragraphs[-1]._element.xpath(".//w:drawing"):
				last = cell.paragraphs[-1]._element
				last.getparent().remove(last)
			if fill:
				_shade(cell, fill)
		# A paragraph after the table, so two tables in a row do not run together.
		gap = sink.paragraph()
		gap.paragraph_format.space_after = Pt(4)
		self.last_table = (gap, table_classes)

	@staticmethod
	def column_widths(el, ncols):
		"""Each column's width, from the table's <colgroup> percentages; the rest shared."""
		pct = []
		for col in el.find_all("col"):
			m = re.search(r"width:\s*([\d.]+)%", col.get("style") or "")
			pct.append(float(m.group(1)) if m else None)
		pct = (pct + [None] * ncols)[:ncols]
		known = sum(p for p in pct if p)
		free = [i for i, p in enumerate(pct) if not p]
		rest = max(100 - known, 0) / len(free) if free else 0
		pct = [p or rest or 100 / ncols for p in pct]
		total = sum(pct) or 100
		return [int(TEXT_W * p / total) for p in pct]

	# ------------------------------------------------------------------ pictures
	def image_width(self, img):
		classes = set(img.get("class") or [])
		if "a3s3-layout" in classes:
			return Cm(13)
		if img.find_parent("td"):
			return Cm(3.2)
		return Cm(6)

	def picture(self, p, src, width):
		"""Add the image at `src` to paragraph p; False when it cannot be read."""
		data = _image_bytes(src)
		if not data:
			return False
		try:
			p.add_run().add_picture(io.BytesIO(data), width=width)
		except Exception:
			# A format Word's writer does not take (WebP, SVG...): as PNG, through Pillow.
			try:
				from PIL import Image

				out = io.BytesIO()
				Image.open(io.BytesIO(data)).save(out, "PNG")
				p.add_run().add_picture(io.BytesIO(out.getvalue()), width=width)
			except Exception:
				return False
		return True


def _image_bytes(src):
	"""The bytes behind an <img src>: a data URI, an /assets path or a site file."""
	if not src:
		return None
	src = src.strip()
	if src.startswith("data:"):
		head, _, body = src.partition(",")
		if "svg" in head:
			return None
		try:
			return base64.b64decode(body) if ";base64" in head else body.encode()
		except Exception:
			return None
	path = re.sub(r"^https?://[^/]+", "", src).split("?")[0]
	if path.startswith("/assets/"):
		full = os.path.join(frappe.local.sites_path, path.lstrip("/"))
		if os.path.isfile(full):
			with open(full, "rb") as f:
				return f.read()
		return None
	if path.startswith(("/files/", "/private/files/")):
		name = frappe.db.get_value("File", {"file_url": path}, "name")
		if name:
			try:
				return frappe.get_doc("File", name).get_content()
			except Exception:
				return None
	return None


def _continues(page):
	"""Whether an inner page only carries on the one before: it opens with a table without a
	header row (the components' rest) or a numbered list that does not start at 1."""
	body = page.select_one(".a3l-body") or page
	first = body.find(["h1", "h2", "h3", "h4", "p", "table", "ol", "ul"])
	if first is None:
		return False
	if first.name == "table":
		return first.find("th") is None
	if first.name == "ol":
		return int(first.get("start") or 1) > 1
	return False


def _shade(cell, hex_fill):
	props = cell._tc.get_or_add_tcPr()
	shd = OxmlElement("w:shd")
	shd.set(qn("w:val"), "clear")
	shd.set(qn("w:color"), "auto")
	shd.set(qn("w:fill"), hex_fill)
	props.append(shd)


def _roman(n):
	out = ""
	for value, numeral in ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
		while n >= value:
			out, n = out + numeral, n - value
	return out
