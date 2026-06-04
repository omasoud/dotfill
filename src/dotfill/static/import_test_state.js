export function serviceIdForTarget(targetKey, services) {
  const service = (services || []).find((s) => s.token_var === targetKey);
  return service ? service.service_id : null;
}

export function canTestImportRow(row, services) {
  return Boolean(
    row &&
      row.target_key &&
      row.status !== "unmapped" &&
      row.status !== "no_change" &&
      serviceIdForTarget(row.target_key, services)
  );
}

export function importTestRequest(scan, row) {
  return {
    path: "/api/import/test",
    body: {
      scanId: scan ? scan.scan_id : "",
      sourceKey: row ? row.source_key : "",
      targetKey: row ? row.target_key : "",
    },
  };
}

export function importTestStatus(states, row) {
  const entry = states && row ? states[row.source_key] : null;
  return entry ? entry.status : "untested";
}

export function setImportTestState(states, sourceKey, status) {
  return {
    ...(states || {}),
    [sourceKey]: { status },
  };
}

export function clearImportTestState(states, sourceKey) {
  const next = { ...(states || {}) };
  delete next[sourceKey];
  return next;
}

export function resetImportTestStates() {
  return {};
}
