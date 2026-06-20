"""Parse the BSE corporate-actions calendar export into canonical records.

This feed is a dated calendar (ex/record/payment dates), not a transaction feed,
so it has no rupee value or volume. Its value is the per-company event timeline
and the cross-reference against insider activity (joined on security code).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .. import normalize as nz
from ..util import col, read_csv_dicts


def parse(path: str | Path) -> Iterator[dict]:
    for i, r in enumerate(read_csv_dicts(path)):
        purpose = col(r, "Purpose")
        company = col(r, "Company Name") or col(r, "Security Name")
        yield {
            "source": "BSE",
            "security_code": col(r, "Security Code"),
            "symbol": col(r, "Security Name"),
            "company": company,
            "company_norm": nz.normco(company),
            "purpose": purpose,
            "category": nz.corp_action_bucket(purpose),
            "ex_date": nz.iso(nz.parse_date(col(r, "Ex Date"))),
            "record_date": nz.iso(nz.parse_date(col(r, "Record Date"))),
            "bc_start": nz.iso(nz.parse_date(col(r, "BC Start"))),
            "bc_end": nz.iso(nz.parse_date(col(r, "BC End"))),
            "nd_start": nz.iso(nz.parse_date(col(r, "ND Start"))),
            "nd_end": nz.iso(nz.parse_date(col(r, "ND End"))),
            "payment_date": nz.iso(nz.parse_date(col(r, "Actual Payment"))),
            "raw_index": i,
        }
