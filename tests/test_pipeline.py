"""Tests for the PromoterPulse pipeline, run against the real sample exports in
data/raw/ (they double as fixtures). Runnable two ways:

    python3 tests/run_tests.py     # stdlib runner, zero dependencies
    pytest                         # if installed

The hard-coded counts are tied to the committed sample files; if those files are
replaced, update the expected numbers (they document the pipeline's behavior).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import match, normalize as nz, sanitize  # noqa: E402
from pipeline.parsers import bse_corpactions, bse_insider, nse_insider  # noqa: E402

BSE_CSV = ROOT / "data/raw/insider/bse/BSE_SEBI_PIT170626.csv"
NSE_CSV = ROOT / "data/raw/insider/nse/NSE_CF-Insider-Trading-17-03-2026-to-17-06-2026.csv"
CORP_CSV = ROOT / "data/raw/corporate_actions/bse/BSE_All_Corporate_Actions.csv"


# --------------------------------------------------------------------------- #
# normalization
# --------------------------------------------------------------------------- #

def test_normco_strips_suffix_variants():
    assert nz.normco("Ravindra Energy Limited") == nz.normco("Ravindra Energy Ltd")
    assert nz.normco("Thomas Cook  (India)  Limited") == nz.normco("Thomas Cook (India) Ltd")
    assert nz.normco("Info Edge (India) Ltd") == nz.normco("Info Edge (India) Limited")


def test_txn_type_canonicalization():
    assert nz.canon_txn_type("Acquisition") == "BUY"
    assert nz.canon_txn_type("Buy") == "BUY"
    assert nz.canon_txn_type("Disposal") == "SELL"
    assert nz.canon_txn_type("Sell") == "SELL"
    assert nz.canon_txn_type("Pledge Revoke") == "REVOKE"
    assert nz.canon_txn_type("Pledge Invoke") == "INVOKE"


def test_category_canonicalization():
    assert nz.canon_category("KMP") == nz.canon_category("Key Managerial Personnel") == "KMP"
    assert nz.canon_category("Promoter") == nz.canon_category("Promoters") == "PROMOTER"
    assert nz.canon_category("Promoter & Director") == nz.canon_category("Promoter and Director")


def test_mode_canonicalization_and_market_flag():
    assert nz.canon_mode("Creation Of Pledge") == nz.canon_mode("Pledge Creation")
    assert nz.canon_mode("Inter-se Transfer") == nz.canon_mode("Inter-se-Transfer")
    assert nz.is_market_mode(nz.canon_mode("Market Purchase")) is True
    assert nz.is_market_mode(nz.canon_mode("ESOP")) is False
    assert nz.is_market_mode(nz.canon_mode("Gift")) is False


def test_date_parsing_both_formats():
    assert nz.parse_date("23 Dec 2024") == date(2024, 12, 23)
    assert nz.parse_date("29-Apr-2026") == date(2026, 4, 29)
    assert nz.parse_date("02-May-2026 16:46") == date(2026, 5, 2)
    assert nz.parse_date("-") is None and nz.parse_date("") is None


def test_corp_action_bucketing():
    assert nz.corp_action_bucket("Bonus issue 4:1") == "BONUS"
    assert nz.corp_action_bucket("Buy Back of Shares") == "BUYBACK"
    assert nz.corp_action_bucket("Right Issue of Equity Shares") == "RIGHTS"
    assert nz.corp_action_bucket("Interim Dividend - Rs 5") == "DIVIDEND"


# --------------------------------------------------------------------------- #
# parsing — counts and full vocabulary coverage on the real files
# --------------------------------------------------------------------------- #

def test_parser_row_counts():
    assert len(list(bse_insider.parse(BSE_CSV))) == 4815
    assert len(list(nse_insider.parse(NSE_CSV))) == 1592
    assert len(list(bse_corpactions.parse(CORP_CSV))) == 675


def test_no_unmapped_vocabulary_in_real_data():
    nz.reset_unmapped()
    list(bse_insider.parse(BSE_CSV))
    list(nse_insider.parse(NSE_CSV))
    unmapped = nz.unmapped()
    assert unmapped["txn_type"] == set(), unmapped["txn_type"]
    assert unmapped["category"] == set(), unmapped["category"]
    assert unmapped["mode"] == set(), unmapped["mode"]


def test_nse_extras_present():
    nse = list(nse_insider.parse(NSE_CSV))
    assert all(r["xbrl"] and r["xbrl"].startswith("http") for r in nse if r["xbrl"])
    assert sum(1 for r in nse if r["regulation"]) > 1500
    assert sum(1 for r in nse if r["xbrl"]) == 1592


# --------------------------------------------------------------------------- #
# matching / dedup
# --------------------------------------------------------------------------- #

def test_within_bse_dedup_collapses_known_duplicates():
    bse = list(bse_insider.parse(BSE_CSV))
    sanitize.sanitize(bse)
    _, stats = match.dedupe_within_source(bse)
    # Matches the user's observed "418 cases" of within-BSE duplication.
    assert stats["dup_groups"] == 346
    assert stats["collapsed_rows"] == 418


def test_cross_feed_merges_majority_of_nse():
    bse = list(bse_insider.parse(BSE_CSV))
    nse = list(nse_insider.parse(NSE_CSV))
    sanitize.sanitize(bse + nse)
    bse, _ = match.dedupe_within_source(bse)
    nse, _ = match.dedupe_within_source(nse)
    _, stats = match.merge_cross_feed(bse, nse)
    assert stats["merged"] == 1048
    assert stats["nse_only"] == 464
    # A clear majority of (deduped) NSE rows are folded into BSE.
    assert stats["merged"] > stats["nse_only"]


def test_merged_rows_carry_nse_xbrl():
    bse = list(bse_insider.parse(BSE_CSV))
    nse = list(nse_insider.parse(NSE_CSV))
    sanitize.sanitize(bse + nse)
    bse, _ = match.dedupe_within_source(bse)
    nse, _ = match.dedupe_within_source(nse)
    merged, _ = match.merge_cross_feed(bse, nse)
    both = [r for r in merged if r["source"] == "BSE+NSE"]
    assert both, "expected some BSE+NSE merged rows"
    assert sum(1 for r in both if r["xbrl"]) > 0.9 * len(both)


# --------------------------------------------------------------------------- #
# sanitization
# --------------------------------------------------------------------------- #

def test_placeholder_repaired_from_twin():
    bse = list(bse_insider.parse(BSE_CSV))
    sanitize.sanitize(bse)
    # 3B Films Ltd: 696,000 shares recorded as worth ~3 rupees, but a twin row
    # (same person/date/shares) carries the real value -> should be repaired.
    placeholder = [r for r in bse if r["company"].startswith("3B Films")
                   and r["shares"] == 696000 and r["value_raw"] == 3.0]
    assert placeholder, "expected the 3B Films placeholder row in the sample"
    rec = placeholder[0]
    assert rec["value_status"] == "repaired"
    assert rec["value_in_totals"] is True
    assert rec["value"] and rec["value"] > 1000  # real value, not the placeholder


def test_flagged_values_excluded_from_totals():
    bse = list(bse_insider.parse(BSE_CSV))
    sanitize.sanitize(bse)
    flagged = [r for r in bse if r["value_status"] == "flagged"]
    assert flagged, "expected some un-repairable placeholder rows"
    # Every flagged row is a positive tiny/anomalous value, excluded from totals.
    assert all(r["value"] is None for r in flagged)
    assert all(r["value_in_totals"] is False for r in flagged)
    assert all(r["value_raw"] and r["value_raw"] > 0 for r in flagged)


def test_pledges_are_novalue_not_flagged():
    bse = list(bse_insider.parse(BSE_CSV))
    sanitize.sanitize(bse)
    pledges = [r for r in bse if r["txn_type"] == "PLEDGE" and not r["value_raw"]]
    assert pledges
    # A pledge with no rupee value is normal, not a data error.
    assert all(r["value_status"] in ("novalue", "repaired") for r in pledges)


def test_zero_value_buys_are_novalue():
    bse = list(bse_insider.parse(BSE_CSV))
    sanitize.sanitize(bse)
    zero_buys = [r for r in bse if r["txn_type"] == "BUY" and r["value_raw"] == 0]
    assert zero_buys
    assert all(r["value_status"] in ("novalue", "repaired") for r in zero_buys)


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #

def test_full_ingest_shape():
    from pipeline import ingest
    meta = ingest.run()
    ins = meta["insider"]
    assert ins["records"] == 4861
    assert ins["by_source"] == {"BSE": 3349, "BSE+NSE": 1048, "NSE": 464}
    assert ins["value_status"]["flagged"] == 104
    assert ins["value_status"]["derivative"] == 33
    assert meta["corporate_actions"]["records"] == 675
    assert not meta["warnings"], meta["warnings"]
    # generated JSON exists
    assert (ROOT / "docs/data/insider.json").exists()
    assert (ROOT / "docs/data/meta.json").exists()
