export function createImportSourceState() {
  return {
    mode: "empty",
    displayValue: "",
    label: "",
    filename: null,
    content: null,
  };
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
  return {
    path: "/api/import/scan-dropped",
    body: {
      filename: source ? source.filename || "" : "",
      content: source ? source.content || "" : "",
    },
  };
}

export function importSourceLabel(source, scan) {
  return (source && source.label) || (scan && scan.source_label) || "";
}
