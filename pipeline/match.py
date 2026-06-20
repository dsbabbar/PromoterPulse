"""Matching and de-duplication.

Two distinct problems, both keyed on (company_norm, person_norm, date_from, shares):

1. Within-source duplicates: BSE's own export repeats the same disclosure (often
   one sane row beside a placeholder-value sibling). We collapse same-key rows to
   one representative and record how many collapsed (`dup_count`).

2. Cross-feed duplicates: ~69% of NSE rows restate a BSE disclosure. We keep the
   BSE row (primary) and fold NSE's unique extras (XBRL link, Regulation,
   broadcast time, symbol) into it; only genuinely NSE-only rows are added.

Records whose key is incomplete (no parseable date or share count — e.g.
derivative-only rows) are never grouped; each stays as its own record.
"""
from __future__ import annotations


def transaction_key(rec: dict):
    """Return the dedup/match key, or None if the record can't be keyed."""
    if not rec.get("company_norm") or not rec.get("person_norm"):
        return None
    if rec.get("date_from") is None or rec.get("shares") is None:
        return None
    return (rec["company_norm"], rec["person_norm"], rec["date_from"], rec["shares"])


def _value_rank(rec: dict):
    """Sort key to pick the best representative within a duplicate group.

    Prefer: a usable value in totals > non-derivative > larger value.
    """
    return (
        1 if rec.get("value_in_totals") else 0,
        0 if rec.get("is_derivative") else 1,
        rec.get("value") or 0.0,
    )


def dedupe_within_source(records: list[dict]) -> tuple[list[dict], dict]:
    """Collapse same-key duplicates within one source. Returns (records, stats)."""
    groups: dict[tuple, list[dict]] = {}
    passthrough: list[dict] = []
    for rec in records:
        key = transaction_key(rec)
        if key is None:
            passthrough.append(rec)
        else:
            groups.setdefault(key, []).append(rec)

    out: list[dict] = []
    collapsed_rows = 0
    dup_groups = 0
    for key, group in groups.items():
        if len(group) == 1:
            group[0]["dup_count"] = 1
            out.append(group[0])
            continue
        dup_groups += 1
        collapsed_rows += len(group) - 1
        rep = max(group, key=_value_rank)
        rep["dup_count"] = len(group)
        out.append(rep)

    for rec in passthrough:
        rec.setdefault("dup_count", 1)
    out.extend(passthrough)
    return out, {"dup_groups": dup_groups, "collapsed_rows": collapsed_rows}


def merge_cross_feed(primary: list[dict], secondary: list[dict]) -> tuple[list[dict], dict]:
    """Merge a secondary feed (NSE) into a primary one (BSE).

    Secondary rows that match a primary row by key are folded in (the primary row
    is tagged BSE+NSE and gains the secondary's XBRL/Regulation/broadcast/symbol);
    unmatched secondary rows are appended as their own (source-only) records.
    """
    index: dict[tuple, dict] = {}
    for rec in primary:
        key = transaction_key(rec)
        if key is not None:
            index.setdefault(key, rec)

    merged = 0
    nse_only = 0
    extras = ("xbrl", "regulation", "broadcast")
    for rec in secondary:
        key = transaction_key(rec)
        match = index.get(key) if key is not None else None
        if match is not None:
            merged += 1
            match["source"] = "BSE+NSE"
            for field in extras:
                if not match.get(field) and rec.get(field):
                    match[field] = rec[field]
            if not match.get("symbol") and rec.get("symbol"):
                match["symbol"] = rec["symbol"]
        else:
            nse_only += 1
            rec.setdefault("dup_count", 1)
            primary.append(rec)

    return primary, {"merged": merged, "nse_only": nse_only}
