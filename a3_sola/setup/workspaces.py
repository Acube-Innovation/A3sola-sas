# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Moving workspace layouts between the desk and the app.

A workspace is unusual: it is both code and content. The app ships a JSON file, but the
desk lets anybody rearrange cards, change an icon or drop a shortcut - and those edits are
written to the **database only**. Deploying copies the file, so a change made in the desk
on one site is simply not present on the next one. It looks like the deploy failed; nothing
failed, the change was never in the repo.

`export()` closes that loop: it reads the live workspaces and writes them back over the
app's JSON files, so a layout somebody arranged by hand becomes part of the app and travels
with it.

    bench --site <site> execute a3_sola.setup.workspaces.export
    # then: git add -A && git commit && git push

`sync()` is the other direction - push the files into the database without a full migrate,
for when you have edited the JSON by hand.
"""

import glob
import io
import json
import os

import frappe

#: Fields that describe the layout. Everything else on a Workspace is bookkeeping that
#: belongs to the site rather than to the app - who last touched it, and when.
EXPORTED = (
	"name", "label", "title", "icon", "indicator_color", "module", "parent_page",
	"sequence_id", "public", "is_hidden", "content", "hide_custom", "for_user",
	"restrict_to_domain", "type",
)

CHILD_TABLES = ("links", "shortcuts", "roles", "number_cards", "charts", "custom_blocks")

#: Dropped from every child row: ids and timestamps are per-database and would make every
#: export a diff even when nothing changed.
NOISE = ("name", "owner", "creation", "modified", "modified_by", "parent", "parenttype",
         "docstatus", "idx", "doctype")


def _app_files():
	base = os.path.dirname(frappe.get_app_path("a3_sola"))
	found = {}
	for path in glob.glob(os.path.join(base, "a3_sola", "*", "workspace", "*", "*.json")):
		found[json.load(io.open(path))["name"]] = path
	return found


def export(names=None):
	"""Write the live workspaces back over the app's JSON files.

	Run this after arranging a workspace in the desk, then commit. Without it the
	arrangement stays on that one site.
	"""
	files = _app_files()
	wanted = [n.strip() for n in names.split(",")] if isinstance(names, str) else (names or list(files))
	written = []

	for name in wanted:
		path = files.get(name)
		if not path:
			print(f"  {name}: no file in this app - skipped")
			continue
		if not frappe.db.exists("Workspace", name):
			print(f"  {name}: not on this site - skipped")
			continue

		doc = frappe.get_doc("Workspace", name)
		out = {"doctype": "Workspace"}
		for field in EXPORTED:
			value = doc.get(field)
			if value not in (None, ""):
				out[field] = value
		for table in CHILD_TABLES:
			rows = []
			for row in doc.get(table) or []:
				clean = {k: v for k, v in row.as_dict().items()
				         if k not in NOISE and v not in (None, "")}
				if clean:
					rows.append(clean)
			if rows:
				out[table] = rows

		# A fresh timestamp, or `bench migrate` will decide the file is older than the
		# database and skip the very import this export exists to enable.
		out["modified"] = frappe.utils.now()
		out["creation"] = out["modified"]
		out["owner"] = "Administrator"
		out["modified_by"] = "Administrator"
		out.setdefault("idx", 0)

		json.dump(out, io.open(path, "w"), indent=1, sort_keys=False, default=str)
		io.open(path, "a").write("\n")
		written.append((name, os.path.relpath(path, os.path.dirname(frappe.get_app_path("a3_sola")))))
		print(f"  exported {name:20s} -> {os.path.basename(path)}  "
		      f"(icon={doc.icon!r}, {len(doc.links)} links, {len(doc.shortcuts)} shortcuts)")

	if written:
		print("\n  Commit these files or the layout stays on this site:")
		for _name, rel in written:
			print(f"    {rel}")
	return [n for n, _ in written]


def sync(names=None):
	"""Push the app's JSON files into the database, without a full migrate."""
	from frappe.modules.import_file import import_file_by_path

	files = _app_files()
	wanted = [n.strip() for n in names.split(",")] if isinstance(names, str) else (names or list(files))
	done = []
	for name in wanted:
		path = files.get(name)
		if not path:
			continue
		import_file_by_path(path, force=True, reset_permissions=False)
		done.append(name)
	frappe.db.commit()
	frappe.clear_cache()

	# Importing bypasses validation. Saving is what proves the file is actually valid -
	# an invalid link type sits in a file quite happily until somebody opens it and saves.
	invalid = []
	for name in done:
		try:
			doc = frappe.get_doc("Workspace", name)
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
		except Exception as exception:
			invalid.append(f"{name}: {exception}")
	frappe.db.commit()
	if invalid:
		print("  INVALID after import - these would fail the moment somebody saves them:")
		for line in invalid:
			print(f"    {line}")
	else:
		print(f"  synced and validated {len(done)} workspace(s)")
	return {"synced": done, "invalid": invalid}
