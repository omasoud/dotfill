// Service card action availability when URL templates need unresolved identities.

export function missingIdentityReason(names) {
  const list = Array.isArray(names) ? names.filter(Boolean) : [];
  if (!list.length) return "";
  return `Needs ${list.join(", ")}`;
}

export function tokenPageAction(svc) {
  if (svc && svc.resolved_token_url) {
    return { available: true, url: svc.resolved_token_url, reason: "" };
  }
  const reason = missingIdentityReason(svc && svc.token_url_unresolved_identities);
  return { available: false, url: null, reason: reason || "Token page unavailable" };
}

export function testAction(svc) {
  if (!svc || !svc.token_present) {
    return { visible: false, available: false, reason: "" };
  }
  if (svc.resolved_test_url) {
    return { visible: true, available: true, reason: "" };
  }
  const reason = missingIdentityReason(svc.test_url_unresolved_identities);
  return { visible: true, available: false, reason: reason || "Test unavailable" };
}

export function serviceMissingHint(svc) {
  const names = [
    ...((svc && svc.token_url_unresolved_identities) || []),
    ...((svc && svc.test_url_unresolved_identities) || []),
  ];
  return missingIdentityReason([...new Set(names)]);
}
