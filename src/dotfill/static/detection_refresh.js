// Automatic dashboard refreshes while identity detection is pending or retrying.

export const POLL_INTERVAL_MS = 2000;
export const RETRY_MARGIN_MS = 250;

// The server's pending deadline shrinks to zero for each pass, so polling
// stops on its own even if a detector never finishes.
// Returns { kind: "poll" | "retry", delayMs } or null when nothing is due.
export function nextDetectionRefresh(detection) {
  if (!detection) return null;
  if (detection.pending) {
    const remaining = Number(detection.pending_deadline_seconds) || 0;
    if (remaining <= 0) return null;
    return { kind: "poll", delayMs: POLL_INTERVAL_MS };
  }
  const retry = detection.next_retry_seconds;
  if (retry === null || retry === undefined) return null;
  return { kind: "retry", delayMs: Math.max(Number(retry) * 1000, 0) + RETRY_MARGIN_MS };
}

export function createDetectionScheduler({ setTimer, clearTimer, refresh }) {
  let handle = null;

  function cancel() {
    if (handle !== null) {
      clearTimer(handle);
      handle = null;
    }
  }

  function update(detection) {
    cancel();
    const next = nextDetectionRefresh(detection);
    if (next) {
      handle = setTimer(() => {
        handle = null;
        refresh();
      }, next.delayMs);
    }
    return next;
  }

  return { update, cancel };
}
