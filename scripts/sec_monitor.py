"""SEC filing monitor: sourced event candidates, not verified interpretations.

Uses public SEC submissions metadata and companyfacts XBRL. US issuers only.
Set SEC_USER_AGENT to an identifiable contact in GitHub Actions repository variables.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path("data")
ROOT.mkdir(exist_ok=True)
STATE = ROOT / "sec_events.json"
WATCHLIST = ["NFLX","SE","NKE","AEVA","KULR","OKLO","FIG","RIVN","BIDU","ASTS","AAOI","LULU","SOFI","UBER","SYF","CROX","PYPL","DECK"]
USER_AGENT = os.getenv("SEC_USER_AGENT", "StockRadarResearch stockradar-research@example.org")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
SEC = "https://data.sec.gov"

def get_json(url):
    response = SESSION.get(url, timeout=25)
    response.raise_for_status()
    return response.json()

def classify(form, items):
    if form in ("10-Q", "10-K", "10-Q/A", "10-K/A"):
        return ["financial_report", "financial_risk_review", "dilution_review"]
    if form in ("S-3", "424B5", "424B2", "S-1", "S-3ASR", "POS AM"):
        return ["potential_dilution"]
    if form == "8-K":
        codes = {x.strip() for x in (items or "").split(",")}
        tags = []
        if "2.02" in codes: tags.append("earnings_release")
        if "1.01" in codes or "1.02" in codes: tags.append("contract_review")
        if "3.02" in codes: tags.append("potential_dilution")
        if "2.03" in codes or "2.04" in codes: tags.append("debt_review")
        if "7.01" in codes or "8.01" in codes: tags.append("project_or_other_event_review")
        return tags
    return []

def main():
    old = {}
    if STATE.exists():
        try: old = json.loads(STATE.read_text(encoding="utf-8"))
        except (ValueError, OSError): pass
    tickers = get_json("https://www.sec.gov/files/company_tickers.json")
    mapping = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in tickers.values()}
    previous_ids = set(old.get("seen_ids", []))
    events, errors, current_ids = [], {}, set(previous_ids)
    for ticker in WATCHLIST:
        cik = mapping.get(ticker)
        if not cik:
            errors[ticker] = "No matching SEC ticker; possibly non-US issuer or alternate ticker"
            continue
        try:
            filing = get_json(f"{SEC}/submissions/CIK{cik}.json")
            recent = filing.get("filings", {}).get("recent", {})
            fields = ["accessionNumber", "form", "filingDate", "primaryDocument", "items"]
            rows = zip(*(recent.get(f, []) for f in fields))
            for accession, form, date, document, items in rows:
                if date < "2026-01-01": break
                tags = classify(form, items)
                if not tags: continue
                event_id = f"{cik}:{accession}"
                current_ids.add(event_id)
                if event_id in previous_ids: continue
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"
                events.append({"ticker": ticker, "filing_date": date, "form": form,
                               "items": items, "categories": tags, "url": url,
                               "status": "review_required",
                               "note": "SEC filing classification only. Revenue, EPS, consensus, cash burn, debt and contract terms NOT extracted or verified."})
            time.sleep(0.15)
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors[ticker] = str(exc)[:220]
    # On first execution, baseline existing filings to avoid a flood of old events.
    if not old.get("initialized"):
        events = []
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "initialized": True,
        "seen_ids": sorted(current_ids)[-4000:],
        "events": sorted(events, key=lambda e: (e["filing_date"], e["ticker"]), reverse=True)[:150],
        "errors": errors,
        "disclaimer": "SEC event candidates; no earnings beats/misses, cash burn deltas or confirmed contracts without primary-document extraction and consensus source.",
    }
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SEC event candidates: {len(payload['events'])}; errors: {len(errors)}")

if __name__ == "__main__":
    main()
