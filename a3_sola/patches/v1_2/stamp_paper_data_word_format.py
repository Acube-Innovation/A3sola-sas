# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stamp paper data sheet, laid out as the Word file "Data for Stamp Paper" is. For a
template still as first seeded; an edited body stays."""

from a3_sola.patches.v1_2.loan_documents_word_format import replace_seeded

#: md5 of the body as first seeded.
SEEDED = {"STAMP-PAPER-DATA": "44b847d0fe60dd5a533e98886f4893bf"}


def execute():
	replace_seeded(SEEDED)
