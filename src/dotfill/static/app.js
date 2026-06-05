// dotfill local web UI - vanilla ES module
// Only the non-secret theme preference is persisted; the session token stays
// in this module scope.

import {
  browseImportSource,
  createImportSourceState,
  dropImportSource,
  editImportSource,
  importSourceLabel,
  importSourceRequest,
  pathImportSource,
} from "./import_source_state.js";
import {
  canTestImportRow,
  clearImportTestState,
  importTestRequest,
  importTestStatus,
  resetImportTestStates,
  setImportTestState,
} from "./import_test_state.js";
import {
  applyTheme,
  nextTheme,
  resolveInitialTheme,
  storeTheme,
} from "./theme_state.js";

let sessionToken = null;
let state = null;
let appVersion = "";
let activeTheme = applyTheme(resolveInitialTheme());

const $ = (sel, root = document) => root.querySelector(sel);

function icon(name, klass = "icon") {
  const requested = name || "key";
  const safe = document.getElementById(`ic-${requested}`) ? requested : "key";
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("class", klass);
  s.setAttribute("aria-hidden", "true");
  const u = document.createElementNS("http://www.w3.org/2000/svg", "use");
  u.setAttribute("href", `#ic-${safe}`);
  s.appendChild(u);
  return s;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) node.setAttribute(k, "");
    else if (v !== false && v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null || child === false) continue;
    if (Array.isArray(child)) child.forEach((c) => c && node.appendChild(c));
    else if (typeof child === "string") node.appendChild(document.createTextNode(child));
    else node.appendChild(child);
  }
  return node;
}

async function api(method, path, body) {
  const headers = { "Accept": "application/json" };
  if (sessionToken) headers["X-Dotfill-Session"] = sessionToken;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let detail;
    try {
      const j = await r.json();
      detail = j.message || j.detail || JSON.stringify(j);
    } catch {
      detail = r.statusText;
    }
    throw new Error(`${r.status} ${detail}`);
  }
  if (r.status === 204) return null;
  return r.json();
}

function showError(message) {
  const region = $("#error-region");
  region.innerHTML = "";
  if (!message) return;
  region.appendChild(
    el("div", { class: "error-banner" }, icon("alert"), message)
  );
}

async function bootstrap() {
  const url = new URL(window.location.href);
  const urlToken = url.searchParams.get("session");
  if (urlToken) {
    sessionToken = urlToken;
    // Remove from URL to avoid lingering in any address bar.
    url.searchParams.delete("session");
    window.history.replaceState({}, "", url.toString());
  }
  // Always fetch bootstrap to get version (and session token as fallback).
  const data = await api("GET", "/api/bootstrap");
  if (!sessionToken) sessionToken = data.session_token;
  appVersion = data.version || "";
}

async function loadState() {
  try {
    state = await api("GET", "/api/state");
    render();
  } catch (e) {
    showError(`Failed to load state: ${e.message}`);
  }
}

function badgeFor(status) {
  const labels = {
    set: "Set",
    missing: "Missing",
    working: "Working",
    failed: "Failed",
    testing: "Testing...",
  };
  return el("span", { class: `badge badge-${status}` }, labels[status] || status);
}

function derivedBadge(status) {
  const map = {
    aligned: ["set", "Aligned"],
    diverged: ["failed", "Diverged"],
    missing: ["missing", "Missing"],
    unresolved: ["missing", "Unresolved"],
  };
  const [klass, label] = map[status] || ["set", status];
  return el("span", { class: `badge badge-${klass}` }, label);
}

function renderDetected() {
  if (!state.identities.length) {
    return el(
      "div",
      { class: "id-section" },
      el("div", { class: "id-section-title" }, "Identities"),
      el("div", { class: "empty-inline" }, "No identities configured.")
    );
  }
  const statusLabel = { detected: "Detected", aligned: "Aligned", diverged: "Diverged", unresolved: "Unresolved" };
  const rows = state.identities.map((i) => {
    const valueText = i.effective_value || "(not detected)";
    const badge = statusLabel[i.source] || i.source;
    const badgeClass = i.source === "diverged" ? "source diverged" : i.source === "unresolved" ? "source unresolved" : "source";
    return el(
      "div",
      { class: "id-row" },
      el("span", { class: "label" }, i.name),
      el(
        "span",
        { class: `value ${i.effective_value ? "" : "empty"}` },
        `= ${valueText}`
      ),
      el("span", { class: badgeClass }, badge)
    );
  });
  return el(
    "div",
    { class: "id-section" },
    el("div", { class: "id-section-title" }, "Identities"),
    ...rows
  );
}

function renderExplicit() {
  const explicit = state.identities.filter((i) => i.source === "diverged");
  if (explicit.length === 0) return null;
  return el(
    "div",
    { class: "id-section" },
    el("div", { class: "id-section-title" }, "Diverged · explicit in .env differs from detected"),
    ...explicit.map((i) =>
      el(
        "div",
        { class: "id-row" },
        el("span", { class: "label" }, i.name),
        el("span", { class: "value" }, `= ${i.explicit_value}`),
        el("span", { class: "source diverged" }, `detected: ${i.detected_value}`)
      )
    )
  );
}

function renderDerived() {
  if (!state.derived.length) return null;
  return el(
    "div",
    { class: "id-section derived-card" },
    el("div", { class: "id-section-title" }, "Derived identity variables"),
    ...state.derived.map((d) => {
      const current = d.current_value || "(missing)";
      return el(
        "div",
        { class: "id-row" },
        el("span", { class: "label" }, d.variable_name),
        el(
          "span",
          { class: `value ${d.current_value ? "" : "empty"}` },
          `= ${current}`
        ),
        derivedBadge(d.status)
      );
    })
  );
}

function renderServices() {
  if (!state.services.length) {
    return el(
      "div",
      { class: "svc-list" },
      el(
        "div",
        { class: "empty-state" },
        el("div", { class: "empty-title" }, "No services configured."),
        el("div", { class: "empty-copy" }, "Run a profile wrapper or edit config.toml.")
      )
    );
  }
  return el(
    "div",
    { class: "svc-list" },
    ...state.services.map((s) => {
      const tokenDisplay = s.token_present
        ? el("span", { class: "svc-token" }, `${s.token_var} = ${s.masked_token}`)
        : el(
            "span",
            { class: "svc-token" },
            el("span", { class: "placeholder" }, `${s.token_var} = (not set)`)
          );

      const buttons = [];
      buttons.push(
        el(
          "button",
          { class: "btn-small", onClick: () => openTokenWizard(s) },
          icon("key"),
          s.token_present ? "Update" : "Set token"
        )
      );
      if (s.token_present) {
        buttons.push(
          el(
            "button",
            { class: "btn-small", onClick: () => testOne(s.service_id) },
            icon("flask"),
            "Test"
          )
        );
      }

      return el(
        "div",
        { class: "svc-card" },
        el(
          "div",
          { class: "svc-left" },
          el("div", { class: "svc-icon" }, icon(s.icon || "key", "icon icon-lg")),
          el(
            "div",
            { class: "svc-meta" },
            el("div", { class: "svc-name" }, s.display_name),
            tokenDisplay
          )
        ),
        el("div", { class: "svc-right" }, badgeFor(s.test_status), ...buttons)
      );
    })
  );
}

function renderConfigDisclosure(configDir) {
  return el(
    "details",
    { class: "df-config-disclosure" },
    el(
      "summary",
      { class: "df-config-summary" },
      icon("arrow-right", "icon df-config-chevron"),
      el("span", {}, "dotfill config")
    ),
    el(
      "div",
      { class: "df-config-panel" },
      icon("folder"),
      el("span", { class: "df-config-path", title: configDir }, configDir),
      el(
        "button",
        {
          class: "path-open-btn",
          onClick: openConfigFolder,
          title: "Open config folder",
          "aria-label": "Open config folder",
        },
        icon("folder")
      )
    )
  );
}

function setTheme(theme) {
  activeTheme = applyTheme(theme);
  storeTheme(activeTheme);
  render();
}

function renderThemeToggle() {
  const targetTheme = nextTheme(activeTheme);
  const label = targetTheme === "dark" ? "Switch to dark mode" : "Switch to light mode";
  return el(
    "button",
    {
      class: "theme-toggle",
      onClick: () => setTheme(targetTheme),
      title: label,
      "aria-label": label,
    },
    icon(activeTheme === "dark" ? "sun" : "moon")
  );
}

function render() {
  const root = $("#root");
  root.innerHTML = "";
  const config = state.config || {};
  const configDir = config.config_dir || "(no config directory)";

  const header = el(
    "div",
    { class: "df-header" },
    el(
      "div",
      { class: "df-header-left" },
      el(
        "div",
        { class: "df-title-row" },
        el("div", { class: "df-title" }, "dotfill"),
        el("span", { class: "df-version" }, `v${appVersion}`)
      ),
      el("div", { class: "df-path" },
        icon("file"),
        el("span", { class: "df-path-text" }, state.env_path),
        el("button", { class: "path-open-btn", onClick: openFolder, title: "Open .env folder", "aria-label": "Open .env folder" }, icon("folder"))
      ),
      renderConfigDisclosure(configDir)
    ),
    el(
      "div",
      { class: "df-header-actions" },
      renderThemeToggle(),
      el(
        "button",
        { onClick: testAll, disabled: !state.services.length },
        icon("flask"),
        "Test all"
      ),
      el(
        "button",
        { onClick: openImportWizard },
        icon("import"),
        "Import"
      ),
      el(
        "button",
        { onClick: loadState },
        icon("refresh"),
        "Refresh"
      )
    )
  );

  const screen = el(
    "div",
    { class: "screen-wrap" },
    header,
    renderDetected(),
    renderExplicit(),
    renderDerived(),
    renderServices(),
    el(
      "div",
      { class: "footer" },
      state.session.backup_path
        ? `Session backup: ${state.session.backup_path}`
        : state.session.backup_created
          ? "Saved (no backup needed — .env was new)"
          : "No save yet this session"
    )
  );

  root.appendChild(screen);
}

// ---- Test actions ----

async function testOne(serviceId) {
  const svc = state.services.find((s) => s.service_id === serviceId);
  if (svc) svc.test_status = "testing";
  render();
  try {
    await api("POST", `/api/test/${serviceId}`);
    await loadState();
  } catch (e) {
    showError(`Test failed: ${e.message}`);
    await loadState();
  }
}

async function openFolder() {
  try {
    await api("POST", "/api/open-folder");
  } catch (e) {
    showError(`Failed to open folder: ${e.message}`);
  }
}

async function openConfigFolder() {
  try {
    await api("POST", "/api/open-config-folder");
  } catch (e) {
    showError(`Failed to open config folder: ${e.message}`);
  }
}

async function testAll() {
  for (const s of state.services) {
    if (s.token_present) s.test_status = "testing";
  }
  render();
  try {
    await api("POST", "/api/test-all");
    await loadState();
  } catch (e) {
    showError(`Test all failed: ${e.message}`);
    await loadState();
  }
}

// ---- Inline Wizards (replace dashboard content) ----

function openTokenWizard(svc) {
  const root = $("#root");
  root.innerHTML = "";

  const input = el("input", {
    type: "text",
    class: "token-input",
    placeholder: "Paste token here",
    autocomplete: "off",
    spellcheck: "false",
  });

  const wizard = el(
    "div",
    { class: "screen-wrap" },
    el(
      "div",
      { class: "wizard-header" },
      el("button", { class: "back-btn", onClick: render }, icon("arrow-left"), ""),
      el("span", { class: "wizard-title" }, `Get new ${svc.display_name} token`),
      el("span", { class: "wizard-target" }, `→ ${svc.token_var}`)
    ),
    el(
      "div",
      { class: "steps" },
      el(
        "div",
        { class: "step" },
        el("div", { class: "step-num" }, "1"),
        el(
          "div",
          { class: "step-body" },
          el("div", { class: "step-text" }, `Open the ${svc.display_name} token page in your browser.`),
          el(
            "div",
            { class: "step-controls" },
            el(
              "a",
              { href: svc.resolved_token_url, target: "_blank", rel: "noopener", class: "btn" },
              icon("external"),
              "Open token page"
            ),
            el("span", { class: "step-meta" }, svc.resolved_token_url)
          )
        )
      ),
      el(
        "div",
        { class: "step" },
        el("div", { class: "step-num" }, "2"),
        el(
          "div",
          { class: "step-body" },
          el("div", { class: "step-text" }, "Create a new token and copy it to your clipboard.")
        )
      ),
      el(
        "div",
        { class: "step" },
        el("div", { class: "step-num" }, "3"),
        el(
          "div",
          { class: "step-body" },
          el("div", { class: "step-text" }, "Paste the token below."),
          input,
          el("div", { class: "hint" }, "dotfill only receives the pasted value locally and saves it to your .env file.")
        )
      ),
      el(
        "div",
        { class: "step" },
        el("div", { class: "step-num" }, "4"),
        el(
          "div",
          { class: "step-body" },
          el(
            "div",
            { class: "step-controls" },
            el(
              "button",
              {
                class: "btn-primary",
                onClick: async () => {
                  const token = input.value;
                  if (!token) return;
                  try {
                    await api("POST", `/api/token/${svc.service_id}`, { token });
                    await loadState();
                  } catch (e) {
                    showError(`Save failed: ${e.message}`);
                  }
                },
              },
              "Save to .env"
            ),
            el("button", { onClick: render }, "Cancel")
          )
        )
      )
    )
  );

  root.appendChild(wizard);
  setTimeout(() => input.focus(), 0);
}

function openImportWizard() {
  const root = $("#root");
  root.innerHTML = "";

  const pathInput = el("input", { type: "text", class: "path-input", placeholder: "Path to .env-like file" });
  const fileInput = el("input", { type: "file", accept: ".env,text/plain", style: "display:none" });
  const tableHost = el("div", {});
  let currentScan = null;
  let activeSource = createImportSourceState();
  let importTestStates = resetImportTestStates();

  pathInput.addEventListener("input", () => {
    activeSource = editImportSource(activeSource, pathInput.value);
    currentScan = null;
    importTestStates = resetImportTestStates();
    renderTable();
  });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    const content = await file.text();
    activeSource = browseImportSource(activeSource, file.name, content);
    pathInput.value = activeSource.displayValue;
    importTestStates = resetImportTestStates();
    await loadScanFromActiveSource();
    fileInput.value = "";
  });

  async function loadScanFromActiveSource() {
    showError("");
    importTestStates = resetImportTestStates();
    renderTable();
    if (activeSource.mode === "path") {
      activeSource = pathImportSource(pathInput.value);
    }
    const request = importSourceRequest(activeSource);
    if (activeSource.mode === "path" && !request.body.path) return;
    if (activeSource.mode !== "path" && !request.body.filename) return;
    try {
      currentScan = await api("POST", request.path, request.body);
      renderTable();
    } catch (e) {
      showError(`Scan failed: ${e.message}`);
    }
  }

  function targetOptions(row) {
    const allTargets = new Set();
    state.services.forEach((s) => allTargets.add(s.token_var));
    state.derived.forEach((d) => allTargets.add(d.variable_name));
    if (row.target_key) allTargets.add(row.target_key);
    const options = [el("option", { value: "" }, "(skip)")];
    [...allTargets]
      .sort()
      .forEach((t) => {
        const opt = el("option", { value: t }, t);
        if (t === row.target_key) opt.selected = true;
        options.push(opt);
      });
    return options;
  }

  function recomputeStatus(row) {
    if (!row.target_key) {
      row.status = "unmapped";
    } else if (row._originalTarget === row.target_key && row._originalStatus) {
      // Reverted to original target — use original server-computed status.
      row.status = row._originalStatus;
    } else {
      // Remapped to a different target.
      const occupied = currentScan.occupied_targets || [];
      row.status = occupied.includes(row.target_key) ? "replace" : "new";
    }
  }

  function computeSummary() {
    if (!currentScan) return "";
    const rows = currentScan.rows;
    const willChange = rows.filter((r) => r.status === "new" || r.status === "replace").length;
    const noChange = rows.filter((r) => r.status === "no_change").length;
    const unmapped = rows.filter((r) => !r.target_key).length;
    const source = importSourceLabel(activeSource, currentScan);
    const prefix = source ? `Source: ${source} · ` : "";
    return `${prefix}Found ${rows.length} candidate variables · ${willChange} will change, ${noChange} already matches, ${unmapped} unmapped`;
  }

  function importTestCell(row) {
    if (!canTestImportRow(row, state.services)) {
      return el("td", { class: "import-test-cell" }, "");
    }
    const rowStatus = importTestStatus(importTestStates, row);
    const children = rowStatus === "working"
      ? [icon("check")]
      : rowStatus === "failed"
        ? [icon("x")]
        : rowStatus === "testing"
          ? ["..."]
          : [icon("flask")];
    const title = rowStatus === "untested"
      ? "Test this service using the imported API key"
      : rowStatus === "testing"
        ? "Testing imported API key"
        : rowStatus === "working"
          ? "Test passed"
          : "Test failed";
    return el(
      "td",
      { class: "import-test-cell" },
      el(
        "button",
        {
          class: `import-test-btn import-test-${rowStatus}`,
          disabled: rowStatus === "testing",
          title,
          "aria-label": title,
          onClick: () => testImportRow(row),
        },
        ...children
      )
    );
  }

  async function testImportRow(row) {
    if (!currentScan || !canTestImportRow(row, state.services)) return;
    const scanId = currentScan.scan_id;
    const sourceKey = row.source_key;
    const targetKey = row.target_key;
    const request = importTestRequest(currentScan, row);
    showError("");
    importTestStates = setImportTestState(importTestStates, sourceKey, "testing");
    renderTable();
    try {
      const result = await api("POST", request.path, request.body);
      if (!currentScan || currentScan.scan_id !== scanId) return;
      const latestRow = currentScan.rows.find((r) => r.source_key === sourceKey);
      if (!latestRow || latestRow.target_key !== targetKey) return;
      importTestStates = setImportTestState(
        importTestStates,
        sourceKey,
        result.status === "working" ? "working" : "failed"
      );
      renderTable();
    } catch (e) {
      if (currentScan && currentScan.scan_id === scanId) {
        importTestStates = setImportTestState(importTestStates, sourceKey, "failed");
        renderTable();
      }
      showError(`Import test failed: ${e.message}`);
    }
  }

  function renderTable() {
    tableHost.innerHTML = "";
    if (!currentScan) {
      updateFooter();
      return;
    }

    const summaryEl = el("div", { class: "summary-line" }, computeSummary());

    const rows = currentScan.rows.map((r, idx) => {
      // Store original mapping for revert detection.
      if (r._originalTarget === undefined) {
        r._originalTarget = r.target_key;
        r._originalStatus = r.status;
      }
      const select = el("select", {
        onChange: (e) => {
          currentScan.rows[idx].target_key = e.target.value || null;
          recomputeStatus(currentScan.rows[idx]);
          importTestStates = clearImportTestState(importTestStates, r.source_key);
          renderTable();
        },
      }, ...targetOptions(r));
      const statusBadge = badgeFor(
        r.status === "no_change" ? "set" : r.status === "new" ? "missing" : r.status === "replace" ? "testing" : "failed"
      );
      statusBadge.textContent = r.status === "no_change" ? "No change" : r.status.charAt(0).toUpperCase() + r.status.slice(1);
      return el(
        "tr",
        { class: r.status === "no_change" ? "dim" : "" },
        el("td", { class: "mono" }, r.source_key),
        el("td", { class: "mono" }, r.masked_source_value || ""),
        el("td", {}, select),
        importTestCell(r),
        el("td", {}, statusBadge)
      );
    });
    const table = el(
      "table",
      { class: "mapping-table" },
      el(
        "thead",
        {},
        el(
          "tr",
          {},
          el("th", {}, "Found in source"),
          el("th", {}, "Value"),
          el("th", {}, "Save as"),
          el("th", { class: "import-test-header", "aria-label": "Test imported service" }, ""),
          el("th", {}, "Status")
        )
      ),
      el("tbody", {}, ...rows)
    );

    tableHost.appendChild(summaryEl);
    tableHost.appendChild(table);

    // Update footer button
    updateFooter();
  }

  function getChangeCount() {
    if (!currentScan) return 0;
    return currentScan.rows.filter((r) => r.status === "new" || r.status === "replace").length;
  }

  let importBtn;
  function updateFooter() {
    const n = getChangeCount();
    if (importBtn) {
      importBtn.textContent = n > 0 ? `Import ${n} variables` : "Nothing to import";
      importBtn.disabled = n === 0;
    }
  }

  // Build dropzone
  const dropzone = el(
    "div",
    { class: "dropzone" },
    el("div", { class: "dropzone-icon" }, icon("cloud-upload", "icon icon-xl")),
    el("div", { class: "dropzone-primary" }, "Drop a .env file here"),
    el("div", { class: "dropzone-secondary" }, "or paste a path below")
  );

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("drag-over");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("drag-over");
  });
  dropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag-over");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    const content = await file.text();
    activeSource = dropImportSource(activeSource, file.name, content);
    pathInput.value = activeSource.displayValue;
    importTestStates = resetImportTestStates();
    await loadScanFromActiveSource();
  });

  importBtn = el(
    "button",
    {
      class: "btn-primary",
      disabled: true,
      onClick: async () => {
        if (!currentScan || getChangeCount() === 0) return;
        try {
          await api("POST", "/api/import/commit", {
            scanId: currentScan.scan_id,
            mappings: currentScan.rows.map((r) => ({
              sourceKey: r.source_key,
              targetKey: r.target_key,
            })),
          });
          await loadState();
        } catch (e) {
          showError(`Commit failed: ${e.message}`);
        }
      },
    },
    "Nothing to import"
  );

  const wizard = el(
    "div",
    { class: "screen-wrap" },
    el(
      "div",
      { class: "wizard-header" },
      el("button", { class: "back-btn", onClick: render }, icon("arrow-left"), ""),
      el("span", { class: "wizard-title" }, "Import from another .env")
    ),
    el(
      "div",
      { class: "wizard-helper" },
      "Values are copied into ",
      el("span", { class: "mono" }, state.env_path),
      ". The source file is not modified."
    ),
    dropzone,
    el(
      "div",
      { class: "path-row" },
      pathInput,
      el("button", { onClick: () => fileInput.click() }, "Browse"),
      el("button", { onClick: loadScanFromActiveSource }, "Scan")
    ),
    tableHost,
    el(
      "div",
      { class: "footer-actions" },
      el("button", { onClick: render }, "Cancel"),
      importBtn
    ),
    fileInput
  );

  root.appendChild(wizard);
}

// ---- Bootstrap ----
(async () => {
  try {
    await bootstrap();
    await loadState();
  } catch (e) {
    showError(`Bootstrap failed: ${e.message}`);
  }
})();
