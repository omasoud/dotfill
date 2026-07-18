// Per-variable request state for derived-default dashboard actions.

export function createDerivedDefaultState() {
  return new Set();
}

export function beginDerivedDefault(state, variableName) {
  if (state.has(variableName)) return false;
  state.add(variableName);
  return true;
}

export function finishDerivedDefault(state, variableName) {
  state.delete(variableName);
}

export function isDerivedDefaultInFlight(state, variableName) {
  return state.has(variableName);
}
