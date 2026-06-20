"""Build the coverage/freshness metadata that powers the data-trust panel."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone


def _date_span(values) -> dict:
    dates = sorted(v for v in values if v)
    return {"min": dates[0] if dates else None, "max": dates[-1] if dates else None}


def build_meta(*, insider, corp, raw_counts, dedup, merge, value_stats, unmapped) -> dict:
    """Assemble the meta.json structure from final data + pipeline stats."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "insider_bse": {
                "rows_raw": raw_counts.get("bse", 0),
                "transaction_dates": _date_span(
                    r["date_from"] for r in insider if r["source"] != "NSE"
                ),
                "latest_intimation": _date_span(
                    r["date_intimation"] for r in insider if r["source"] != "NSE"
                )["max"],
            },
            "insider_nse": {
                "rows_raw": raw_counts.get("nse", 0),
                "latest_intimation": _date_span(
                    r["date_intimation"] for r in insider if r.get("xbrl")
                )["max"],
            },
            "corporate_actions_bse": {
                "rows_raw": raw_counts.get("corp", 0),
                "event_dates": _date_span(r["ex_date"] for r in corp),
            },
        },
        "insider": {
            "records": len(insider),
            "by_source": dict(Counter(r["source"] for r in insider)),
            "within_bse": dedup.get("bse", {}),
            "within_nse": dedup.get("nse", {}),
            "cross_feed": merge,
            # Reported on the FINAL (deduped) records — what the dashboard shows.
            "value_status": dict(Counter(r["value_status"] for r in insider)),
            "value_status_raw": value_stats,
            "transaction_dates": _date_span(r["date_from"] for r in insider),
        },
        "corporate_actions": {
            "records": len(corp),
            "buckets": dict(Counter(r["category"] for r in corp)),
            "event_dates": _date_span(r["ex_date"] for r in corp),
        },
        "warnings": {
            "unmapped_" + k: sorted(v) for k, v in unmapped.items() if v
        },
    }
