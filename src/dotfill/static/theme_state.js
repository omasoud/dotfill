export const THEME_STORAGE_KEY = "dotfill.theme";

const VALID_THEMES = new Set(["light", "dark"]);

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

function defaultMatchMedia() {
  try {
    return globalThis.matchMedia || null;
  } catch {
    return null;
  }
}

export function normalizeTheme(value) {
  return VALID_THEMES.has(value) ? value : null;
}

export function readStoredTheme(storage = defaultStorage()) {
  if (!storage) return null;
  try {
    return normalizeTheme(storage.getItem(THEME_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function storeTheme(theme, storage = defaultStorage()) {
  const normalized = normalizeTheme(theme);
  if (!normalized || !storage) return false;
  try {
    storage.setItem(THEME_STORAGE_KEY, normalized);
    return true;
  } catch {
    return false;
  }
}

export function preferredSystemTheme(matchMedia = defaultMatchMedia()) {
  if (!matchMedia) return "light";
  try {
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function resolveInitialTheme(options = {}) {
  const stored = readStoredTheme(options.storage);
  return stored || preferredSystemTheme(options.matchMedia);
}

export function nextTheme(theme) {
  return normalizeTheme(theme) === "dark" ? "light" : "dark";
}

export function applyTheme(theme, documentRef = globalThis.document) {
  const normalized = normalizeTheme(theme) || "light";
  if (documentRef && documentRef.documentElement) {
    documentRef.documentElement.dataset.theme = normalized;
    documentRef.documentElement.style.colorScheme = normalized;
  }
  return normalized;
}
