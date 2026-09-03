# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Timing things honestly.

Two decisions worth stating, because they change what the numbers mean:

*Percentiles, not averages.* A mean hides the tail, and the tail is what a user
experiences as "the system is slow". p95 and p99 are the numbers worth quoting.

*Query counts alongside milliseconds.* Wall time on a developer's laptop with a warm cache
does not transfer to a production host. A query count does: a report issuing 400 queries
issues 400 queries everywhere, and that is what an N+1 audit acts on.
"""

import statistics
import time
from contextlib import contextmanager

import frappe


class Timing:
	"""The result of running one thing several times."""

	__slots__ = ("label", "samples", "queries", "error", "rows")

	def __init__(self, label, samples, queries=0, error=None, rows=None):
		self.label = label
		self.samples = sorted(samples)
		self.queries = queries
		self.error = error
		self.rows = rows

	def _percentile(self, fraction):
		if not self.samples:
			return None
		index = min(len(self.samples) - 1, int(round(fraction * (len(self.samples) - 1))))
		return round(self.samples[index], 1)

	@property
	def p50(self):
		return self._percentile(0.50)

	@property
	def p95(self):
		return self._percentile(0.95)

	@property
	def p99(self):
		return self._percentile(0.99)

	def as_dict(self):
		return {
			"label": self.label,
			"runs": len(self.samples),
			"p50_ms": self.p50, "p95_ms": self.p95, "p99_ms": self.p99,
			"queries": self.queries, "rows": self.rows, "error": self.error,
		}


@contextmanager
def counting_queries():
	"""Count SQL statements for the duration of the block.

	Wraps `frappe.db.sql` rather than reading a debug log, because `frappe.db.sql` is the
	single funnel every query in Frappe goes through - including the query builder, which
	calls it underneath.
	"""
	counter = {"n": 0}
	original = frappe.db.sql

	def counted(*args, **kwargs):
		counter["n"] += 1
		return original(*args, **kwargs)

	frappe.db.sql = counted
	try:
		yield counter
	finally:
		frappe.db.sql = original


def measure(label, call, runs=7, warmup=1):
	"""Run `call` and report percentiles, a query count and any error.

	The warm-up run is discarded: the first call pays for meta loading, controller import
	and cache population, which is real but is not what the user experiences on the
	hundredth request.
	"""
	for _ in range(max(0, warmup)):
		try:
			call()
		except Exception:
			break

	samples, queries, error, rows = [], 0, None, None
	for index in range(runs):
		start = time.perf_counter()
		try:
			if index == 0:
				with counting_queries() as counter:
					result = call()
				queries = counter["n"]
			else:
				result = call()
			if rows is None:
				rows = _row_count(result)
		except Exception as exception:
			error = f"{type(exception).__name__}: {str(exception)[:120]}"
			break
		samples.append((time.perf_counter() - start) * 1000.0)
	return Timing(label, samples, queries=queries, error=error, rows=rows)


def _row_count(result):
	if result is None:
		return None
	if isinstance(result, list):
		return len(result)
	if isinstance(result, dict):
		for key in ("result", "rows", "data", "values"):
			if isinstance(result.get(key), list):
				return len(result[key])
	if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], list):
		return len(result[1])
	return None


def render_table(timings, title=""):
	lines = []
	if title:
		lines += [f"### {title}", ""]
	lines += [
		"| What | p50 ms | p95 ms | p99 ms | Queries | Rows |",
		"|---|---:|---:|---:|---:|---:|",
	]
	for timing in timings:
		if timing.error:
			lines.append(f"| {timing.label} | — | — | — | — | {timing.error} |")
			continue
		lines.append(
			f"| {timing.label} | {timing.p50} | {timing.p95} | {timing.p99} "
			f"| {timing.queries} | {timing.rows if timing.rows is not None else '—'} |"
		)
	return "\n".join(lines)


def render_console(timings, title=""):
	out = [f"--- {title} ---"] if title else []
	out.append("%-52s %8s %8s %8s %7s %7s" % ("what", "p50", "p95", "p99", "queries", "rows"))
	for t in timings:
		if t.error:
			out.append("%-52s  %s" % (t.label[:52], t.error))
			continue
		out.append("%-52s %8s %8s %8s %7s %7s" % (
			t.label[:52], t.p50, t.p95, t.p99, t.queries,
			t.rows if t.rows is not None else "-"))
	return "\n".join(out)
