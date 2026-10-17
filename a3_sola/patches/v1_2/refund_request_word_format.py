# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The registration fee refund request, laid out as the Word file "To The Asst.
Engineer_Refund" is, to download from the Completion File task. For a template still as
first seeded; an edited body stays."""

from a3_sola.patches.v1_2.loan_documents_word_format import replace_seeded

#: md5 of the body as first seeded.
SEEDED = {"KSEB-REFUND-REQUEST": "5648cfcd59d101df6405f8e22100f8fc"}


def execute():
	replace_seeded(SEEDED)
