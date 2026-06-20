// URL-hash router: "#<tab>?<querystring>" so filtered views are shareable.

export function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  const [tab, query = ""] = raw.split("?");
  return { tab: tab || "insider", params: Object.fromEntries(new URLSearchParams(query)) };
}

export function writeHash(tab, obj) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v === "" || v == null || v === false || v === "0") continue;
    p.set(k, Array.isArray(v) ? v.join(",") : String(v));
  }
  const qs = p.toString();
  const next = "#" + tab + (qs ? "?" + qs : "");
  if (next !== location.hash) history.replaceState(null, "", next);
}

export function shareUrl() { return location.href; }
