export function createImportSourceState() {
  return pathImportSource("");
}

export function pathImportSource(value) {
  const displayValue = value || "";
  return {
    mode: "path",
    displayValue,
    label: displayValue,
    filename: null,
    content: null,
  };
}

export function editImportSource(_source, value) {
  return pathImportSource(value);
}

export function browseImportSource(_source, filename, content) {
  const safeFilename = filename || "";
  const label = `Selected file: ${safeFilename}`;
  return {
    mode: "browse",
    displayValue: label,
    label,
    filename: safeFilename,
    content: content || "",
  };
}

export function dropImportSource(_source, filename, content) {
  const safeFilename = filename || "";
  const label = `Dropped file: ${safeFilename}`;
  return {
    mode: "drop",
    displayValue: label,
    label,
    filename: safeFilename,
    content: content || "",
  };
}

export function importSourceRequest(source) {
  if (!source || source.mode === "path") {
    return {
      path: "/api/import/scan-path",
      body: { path: source ? source.displayValue : "" },
    };
  }
  return {
    path: "/api/import/scan-dropped",
    body: {
      filename: source.filename || "",
      content: source.content || "",
    },
  };
}

export function importSourceLabel(source, scan) {
  return (source && source.label) || (scan && scan.source_label) || "";
}
