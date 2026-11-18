# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The latitude and longitude a shared Google Maps link points at.

A link is what people have to hand - copied from the Maps app or the browser - so the
site's coordinates are read from it rather than typed. The shapes it comes in:

- the place's pin, `.../data=!3d10.5276!4d76.2144` - the most exact, so read first;
- a query, `?q=10.5276,76.2144`, `?query=`, `?ll=`, `?center=`, `?destination=`;
- the map's centre, `.../@10.5276,76.2144,17z`;
- the coordinates themselves, "10.5276, 76.2144", pasted as they are;
- a short link from the app's Share button, `maps.app.goo.gl/...`, which is followed to
  the long one first. Only Google's own short-link hosts are followed.

A link to a place by name alone ("?q=Thrissur") has no coordinates, and gives none.
"""

import re
from urllib.parse import parse_qs, unquote, urlparse

import frappe

SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl", "g.co"}
NUMBER = r"(-?\d{1,3}(?:\.\d+)?)"
PIN = re.compile(r"!3d" + NUMBER + r"!4d" + NUMBER)
CENTRE = re.compile(r"@" + NUMBER + r"," + NUMBER)
PAIR = re.compile(r"^\s*" + NUMBER + r"\s*,\s*" + NUMBER + r"\s*$")
QUERY_KEYS = ("q", "query", "ll", "center", "destination", "daddr")


def coordinates(link):
	"""(latitude, longitude) the link points at, or None."""
	link = (link or "").strip()
	if not link:
		return None
	found = _read(link)
	if not found and urlparse(_with_scheme(link)).hostname in SHORT_HOSTS:
		found = _read(_expand(_with_scheme(link)))
	return found


def _read(link):
	text = unquote(link)
	match = PIN.search(text)
	if match and _valid(match.groups()):
		return _pair(match.groups())
	query = parse_qs(urlparse(_with_scheme(link)).query)
	for key in QUERY_KEYS:
		for value in query.get(key, ()):
			match = PAIR.match(value.replace("+", " "))
			if match and _valid(match.groups()):
				return _pair(match.groups())
	# A consent page carries the map's own link in `continue`.
	for value in query.get("continue", ()):
		found = _read(value)
		if found:
			return found
	match = CENTRE.search(text) or PAIR.match(text)
	if match and _valid(match.groups()):
		return _pair(match.groups())
	return None


def _expand(link):
	"""Where a short link leads, or "" when it cannot be followed."""
	import requests

	try:
		response = requests.get(link, timeout=8, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
		return response.url or ""
	except Exception:
		return ""


def _with_scheme(link):
	return link if re.match(r"^[a-z]+://", link, re.I) else "https://" + link


def _valid(groups):
	lat, lng = (float(g) for g in groups)
	return -90 <= lat <= 90 and -180 <= lng <= 180 and (lat, lng) != (0, 0)


def _pair(groups):
	return round(float(groups[0]), 6), round(float(groups[1]), 6)


@frappe.whitelist()
def read_coordinates(link):
	"""For the form, as the link is pasted: {"latitude", "longitude"}, or {} when it has none."""
	found = coordinates(link)
	return {"latitude": found[0], "longitude": found[1]} if found else {}
