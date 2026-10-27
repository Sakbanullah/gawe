"use strict";

/**
 * Which import actions a page read can offer.
 *
 * Kept pure and free of `chrome`/DOM so `node --test` can cover it. The two
 * actions are independent: a split Jobstreet view shows cards on the left and a
 * full description on the right, and both are sendable.
 */
function gaweAvailable(page) {
  const p = page || {};
  return {
    cards: Array.isArray(p.jobs) && p.jobs.length > 0,
    detail: Boolean(p.detail && p.detail.description),
  };
}

// Classic script in the popup, CommonJS under `node --test`.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { gaweAvailable };
}
