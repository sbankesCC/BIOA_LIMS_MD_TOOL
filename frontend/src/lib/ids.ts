// Client-made IDs for changes (CONTRACTS §4a): the UI creates `chg_` IDs so a resent change
// is ignored by the API. Uses getRandomValues, which also works outside secure contexts.

// Bytes of randomness in each ID (128 bits, like a UUID)
const ID_BYTES = 16;

/** Return random hex text of ID_BYTES bytes. */
function makeRandomHex(): string {
  const bytes = new Uint8Array(ID_BYTES);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Return a new change ID such as `chg_3f2a…`. */
export function makeChangeId(): string {
  return `chg_${makeRandomHex()}`;
}
