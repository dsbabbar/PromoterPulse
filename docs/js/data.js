// Data loading, watchlist persistence, filtering, and pure aggregation helpers.

export const state = {
  insider: [], corp: [], openoffers: [], preferential: [], meta: null,
};

async function fetchJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export async function loadAll() {
  const [insider, corp, openoffers, preferential, meta] = await Promise.all([
    fetchJson("data/insider.json"),
    fetchJson("data/corporate_actions.json"),
    fetchJson("data/open_offers.json").catch(() => []),
    fetchJson("data/preferential.json").catch(() => []),
    fetchJson("data/meta.json"),
  ]);
  Object.assign(state, { insider, corp, openoffers, preferential, meta });
  return state;
}

/* ----------------------------- watchlist ------------------------------ */
const WKEY = "ct.watchlist";
export function getWatch() {
  try { return new Set(JSON.parse(localStorage.getItem(WKEY) || "[]")); }
  catch { return new Set(); }
}
export function isWatched(norm) { return getWatch().has(norm); }
export function toggleWatch(norm) {
  const w = getWatch();
  w.has(norm) ? w.delete(norm) : w.add(norm);
  localStorage.setItem(WKEY, JSON.stringify([...w]));
  return w;
}

/* ------------------------------ filtering ----------------------------- */
export function applyInsiderFilters(records, f) {
  const watch = f.watchOnly ? getWatch() : null;
  const q = (f.search || "").trim().toLowerCase();
  return records.filter((r) => {
    if (f.from && (!r.date_from || r.date_from < f.from)) return false;
    if (f.to && (!r.date_from || r.date_from > f.to)) return false;
    if (f.types && f.types.size && !f.types.has(r.txn_type)) return false;
    if (f.cats && f.cats.size && !f.cats.has(r.category)) return false;
    if (f.modes && f.modes.size && !f.modes.has(r.mode)) return false;
    if (f.marketOnly && !r.is_market) return false;
    if (f.promoterOnly && !r.is_promoter) return false;
    if (watch && !watch.has(r.company_norm)) return false;
    if (q && !(r.company.toLowerCase().includes(q) || r.person.toLowerCase().includes(q))) return false;
    return true;
  });
}

/* ---------------------------- aggregations ---------------------------- */
const isBuy = (r) => r.txn_type === "BUY";
const isSell = (r) => r.txn_type === "SELL";
const val = (r) => (r.value_in_totals ? Number(r.value) : 0);

export function totals(records) {
  let buy = 0, sell = 0, companies = new Set(), flagged = 0;
  for (const r of records) {
    if (isBuy(r)) buy += val(r);
    else if (isSell(r)) sell += val(r);
    companies.add(r.company_norm);
    if (r.value_status === "flagged") flagged++;
  }
  return { buy, sell, net: buy - sell, companies: companies.size, rows: records.length, flagged };
}

// company_norm -> { name, code, buy, sell, net, buyers:Set }
export function byCompany(records) {
  const m = new Map();
  for (const r of records) {
    let e = m.get(r.company_norm);
    if (!e) { e = { name: r.company, code: r.security_code || r.symbol, buy: 0, sell: 0, net: 0, buyers: new Set(), sellers: new Set() }; m.set(r.company_norm, e); }
    if (isBuy(r)) { e.buy += val(r); e.buyers.add(r.person_norm); }
    else if (isSell(r)) { e.sell += val(r); e.sellers.add(r.person_norm); }
    e.net = e.buy - e.sell;
  }
  return m;
}

export function dailySeries(records) {
  const m = new Map();
  for (const r of records) {
    if (!r.date_from) continue;
    let e = m.get(r.date_from);
    if (!e) { e = { buy: 0, sell: 0 }; m.set(r.date_from, e); }
    if (isBuy(r)) e.buy += val(r);
    else if (isSell(r)) e.sell += val(r);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

export function categoryValue(records) {
  const m = new Map();
  for (const r of records) {
    const v = val(r);
    if (!v) continue;
    m.set(r.category, (m.get(r.category) || 0) + v);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

// Companies with >=2 distinct insiders buying — a conviction signal.
export function clusterBuying(records) {
  const m = byCompany(records);
  const out = [];
  for (const e of m.values()) {
    if (e.buyers.size >= 2 && e.buy > 0) out.push({ name: e.name, buyers: e.buyers.size, value: e.buy });
  }
  return out.sort((a, b) => b.buyers - a.buyers || b.value - a.value);
}

// Pledge activity per company: shares created vs released (revoke/invoke).
export function pledgeActivity(records) {
  const m = new Map();
  for (const r of records) {
    const t = r.txn_type;
    if (t !== "PLEDGE" && t !== "REVOKE" && t !== "INVOKE") continue;
    let e = m.get(r.company_norm);
    if (!e) { e = { name: r.company, created: 0, released: 0, events: 0 }; m.set(r.company_norm, e); }
    e.events++;
    if (t === "PLEDGE") e.created += r.shares || 0;
    else e.released += r.shares || 0;
  }
  const out = [...m.values()].map((e) => ({ ...e, net: e.created - e.released }));
  return out.sort((a, b) => b.created - a.created);
}

// Companies with net insider buying AND an upcoming corporate action.
export function crossref(insiderRecords, corpRecords) {
  const m = byCompany(insiderRecords);
  const buyingByCode = new Map();
  for (const [norm, e] of m) {
    if (e.net > 0 && e.code) buyingByCode.set(String(e.code), { norm, ...e });
  }
  const out = [];
  for (const c of corpRecords) {
    const hit = buyingByCode.get(String(c.security_code));
    if (hit) out.push({ name: hit.name, net: hit.net, action: c.category, date: c.ex_date, purpose: c.purpose });
  }
  // de-dup by name+action+date, keep soonest date first
  const seen = new Set();
  return out.filter((o) => { const k = o.name + o.action + o.date; if (seen.has(k)) return false; seen.add(k); return true; })
            .sort((a, b) => (b.date || "").localeCompare(a.date || "")); // most recent action first
}
