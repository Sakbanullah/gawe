"use strict";

/**
 * The only part of the extension that talks to Gawe.
 *
 * The content script cannot fetch localhost on its own: page-world requests are
 * subject to the site's CORS and would leak the token to Jobstreet. The popup
 * asks this worker instead, which runs with the extension's own permissions.
 */

const API = "http://127.0.0.1:8000/api/import/browser";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "gawe-import") return false;
  (async () => {
    const { token } = await chrome.storage.local.get("token");
    if (!token) {
      sendResponse({ ok: false, error: "Token belum diisi." });
      return;
    }
    try {
      const response = await fetch(API, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Gawe-Token": token,
        },
        body: JSON.stringify(message.body),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload.error || {};
        sendResponse({
          ok: false,
          status: response.status,
          error: detail.message || `HTTP ${response.status}`,
        });
        return;
      }
      sendResponse({ ok: true, result: payload });
    } catch (error) {
      sendResponse({
        ok: false,
        error: "Gawe tidak dapat dihubungi. Pastikan backend berjalan di 127.0.0.1:8000.",
      });
    }
  })();
  return true; // keep the channel open for the async reply
});
