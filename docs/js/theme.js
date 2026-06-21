// Colour-theme switching, persisted in localStorage. The chosen theme sets a
// `data-theme` attribute on <html>; the CSS variables for that theme cascade to
// everything. Charts re-read CSS variables on each render (see charts.js), so a
// re-render after a theme change is all that's needed to recolour them.

const KEY = "pp.theme";
export const THEMES = ["dark", "light", "midnight", "sepia", "contrast", "auto"];

export function getTheme() {
  const t = localStorage.getItem(KEY);
  return THEMES.includes(t) ? t : "dark";
}

export function applyTheme(name) {
  const t = THEMES.includes(name) ? name : "dark";
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
}

export function initTheme(onChange) {
  const cur = getTheme();
  applyTheme(cur);
  const sel = document.getElementById("themeSelect");
  if (sel) {
    sel.value = cur;
    sel.addEventListener("change", () => { applyTheme(sel.value); onChange?.(); });
  }
  // When in Auto mode, react to the OS switching between light/dark.
  window.matchMedia?.("(prefers-color-scheme: light)")
    .addEventListener("change", () => { if (getTheme() === "auto") onChange?.(); });
}
