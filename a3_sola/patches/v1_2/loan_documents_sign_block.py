# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank pair's signature and seal are marked (`.a3s-sign`), so a loan application can
be printed without them, to sign and stamp by hand. For templates still as the Word-layout
patch left them; an edited body stays."""

from a3_sola.patches.v1_2.loan_documents_word_format import replace_seeded

#: md5 of each body as loan_documents_word_format seeded it.
SEEDED = {
	"BANK-COVERING-LOAN": "1cf03e571213583c6ac1053e765d2a23",
	"BANK-VENDOR-FEASIBILITY": "9198631b6e43dcfd80397a837bc8af13",
}


def execute():
	replace_seeded(SEEDED)
