// Pure formatting helper for package and optional wrapper version metadata.

export function formatVersionDisplay(dotfillVersion, wrapper) {
  const packageLabel = `v${dotfillVersion || ""}`;
  if (
    !wrapper ||
    typeof wrapper.name !== "string" ||
    typeof wrapper.version !== "string" ||
    !wrapper.name ||
    !wrapper.version
  ) {
    return packageLabel;
  }
  return `${packageLabel} (${wrapper.name} v${wrapper.version})`;
}
