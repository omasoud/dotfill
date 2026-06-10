export function recomputeImportRowStatus(row, scan) {
  if (!row || !row.target_key) {
    if (row) row.status = "unmapped";
    return "unmapped";
  }

  const targetStatuses = row.target_statuses || {};
  if (targetStatuses[row.target_key]) {
    row.status = targetStatuses[row.target_key];
    return row.status;
  }

  if (row._originalTarget === row.target_key && row._originalStatus) {
    row.status = row._originalStatus;
    return row.status;
  }

  const occupied = (scan && scan.occupied_targets) || [];
  row.status = occupied.includes(row.target_key) ? "replace" : "new";
  return row.status;
}
