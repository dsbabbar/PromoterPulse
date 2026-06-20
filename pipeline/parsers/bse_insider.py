"""Parse BSE insider-trading (SEBI PIT) exports into canonical records."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .. import normalize as nz
from ..util import col, read_csv_dicts


def parse(path: str | Path) -> Iterator[dict]:
    for i, r in enumerate(read_csv_dicts(path)):
        sec_type_acq = col(r, "Type of Securities Acquired")
        contract_spec = col(r, "Derivative Contract", "Specification")
        shares = nz.parse_num(col(r, "Number of Securities Acquired"))
        is_derivative = (
            "derivative" in sec_type_acq.lower()
            or (shares is None and bool(contract_spec) and contract_spec != "-")
        )

        category = nz.canon_category(col(r, "Category of person"))
        mode = nz.canon_mode(col(r, "Mode of Acquisition"))

        yield {
            "source": "BSE",
            "security_code": col(r, "Security Code"),
            "symbol": "",
            "company": col(r, "Security Name"),
            "company_norm": nz.normco(col(r, "Security Name")),
            "person": col(r, "Name of Person"),
            "person_norm": nz.normp(col(r, "Name of Person")),
            "category_raw": col(r, "Category of person"),
            "category": category,
            "txn_type_raw": col(r, "Transaction Type"),
            "txn_type": nz.canon_txn_type(col(r, "Transaction Type")),
            "mode_raw": col(r, "Mode of Acquisition"),
            "mode": mode,
            "is_market": nz.is_market_mode(mode),
            "is_promoter": nz.is_promoter_category(category),
            "shares": shares,
            "value_raw": nz.parse_num(col(r, "Value of Securities Acquired")),
            "prior_shares": nz.parse_num(col(r, "Number of Securities held Prior")),
            "prior_pct": nz.parse_num(col(r, "% of Securities held Prior")),
            "post_shares": nz.parse_num(col(r, "Number of Securities held Post")),
            "post_pct": nz.parse_num(col(r, "Post-Transaction % of Shareholding")),
            "date_from": nz.iso(nz.parse_date(col(r, "From date"))),
            "date_to": nz.iso(nz.parse_date(col(r, "To date"))),
            "date_intimation": nz.iso(nz.parse_date(col(r, "Date of Intimation"))),
            "is_derivative": is_derivative,
            "exchange_traded": col(r, "Exchange on which"),
            "regulation": None,
            "xbrl": None,
            "broadcast": None,
            "raw_index": i,
        }
