"use strict";

/**
 * Popup: reads the visible cards, sends them once, prints the counts.
 *
 * Nothing here paginates. The user moves to the next page in their own browser;
 * that keeps the traffic indistinguishable from a person browsing.
 *
 * The two sends are independent. On a split Jobstreet view the card list and a
 * job's full description are both on screen, so both buttons can be enabled at
 * once. A detail send is keyed by the URL it already had from the card import;
 * the backend replaces the snippet and re-assesses, so the job stays one row.
 */

const $ = (id) => document.getElementById(id);
const CONTENT_SCRIPT = "content/jobstreet.js";

function describe(result) {
  const lines = [];
  if (result.mode === "detail") {
    if (!result.job_ids || !result.job_ids.length) {
      lines.push("Deskripsi penuh ditolak.");
    } else if (result.created) {
      // No card on record for this URL: the row is new, say so instead of
      // claiming an update that never happened.
      lines.push("Deskripsi penuh tersimpan sebagai lowongan baru.");
    } else if (result.version_added) {
      lines.push("Deskripsi penuh terkirim, versi posting diperbarui.");
    } else {
      lines.push("Deskripsi tidak mengubah versi posting.");
    }
  } else {
    lines.push(
      `${result.accepted} baru, ${result.duplicates} duplikat, ${result.rejected} ditolak.`,
    );
  }
  if (result.eligibility && result.eligibility.status) {
    lines.push(`Eligibility sekarang: ${result.eligibility.status}`);
  }
  if (result.rejected_details && result.rejected_details.length) {
    lines.push("");
    for (const item of result.rejected_details) {
      lines.push(`#${item.index + 1}: ${item.reason}`);
    }
  }
  return lines.join("\n");
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function readPage() {
  const tab = await currentTab();
  if (!tab || !tab.id) throw new Error("Tidak ada tab aktif.");
  if (!/^https:\/\/id\.jobstreet\.com\//.test(tab.url || "")) {
    return { kind: "wrong-host", jobs: [], detail: null, pageUrl: tab.url || "" };
  }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [CONTENT_SCRIPT] });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.gaweReadJobstreet(),
  });
  // A page that is still loading can answer with no value at all; without this
  // guard the next property read throws and the popup shows nothing at all.
  if (!result || !result.kind) throw new Error("Halaman belum siap. Muat ulang lalu coba lagi.");
  return result;
}

/** "Requirements" / "Lamar" sections usually live after the company blurb. */
function likelyMissingRequirements(description) {
  return !/requirement|kualifikasi|qualification|persyaratan/i.test(description || "");
}

async function init() {
  const { token } = await chrome.storage.local.get("token");
  if (token) $("token").value = token;

  let page;
  try {
    page = await readPage();
  } catch (error) {
    $("summary").textContent = error.message;
    return;
  }

  if (page.kind === "wrong-host") {
    $("summary").textContent = "Buka halaman id.jobstreet.com dulu.";
    return;
  }
  if (page.kind === "wrong-page") {
    $("summary").textContent = "Halaman ini bukan hasil pencarian atau detail lowongan.";
    return;
  }

  // The two actions are independent: a split view shows cards on the left and
  // one job's full description on the right, so both buttons can be enabled.
  const available = gaweAvailable(page);
  const lines = [];
  if (available.detail) {
    const warning = likelyMissingRequirements(page.detail.description)
      ? " Deskripsi ini belum memuat bagian persyaratan."
      : "";
    lines.push(`Detail: ${page.detail.title}.${warning}`);
  }
  if (available.cards) {
    lines.push(`Terdeteksi ${page.jobs.length} kartu lowongan di halaman ini.`);
  }
  $("summary").textContent = lines.length
    ? lines.join("\n")
    : "Tidak ada kartu atau deskripsi lowongan yang terbaca. Muat ulang lalu coba lagi.";
  $("send-cards").disabled = !available.cards;
  $("send-detail").disabled = !available.detail;
}

$("save").addEventListener("click", async () => {
  const token = $("token").value.trim();
  await chrome.storage.local.set({ token });
  $("status").textContent = token ? "Token disimpan." : "Token dikosongkan.";
});

function onSend(button, action) {
  $(button).addEventListener("click", async () => {
    try {
      await action();
    } catch (error) {
      $("status").textContent = error.message || "Gagal mengirim.";
    }
  });
}

onSend("send-cards", () => send("cards"));
onSend("send-detail", () => send("detail"));

/** Sends one mode. Both bodies match the backend contract; only one is chosen. */
async function send(mode) {
  const page = await readPage();
  let body;
  if (mode === "detail") {
    if (!page.detail || !page.detail.description) {
      $("status").textContent = "Deskripsi lowongan tidak ditemukan di halaman ini.";
      return;
    }
    // The detail object carries the cleaned identity URL, not the address bar.
    const detail =
      page.detail && page.url ? { ...page.detail, url: page.url } : page.detail;
    body = { source: "jobstreet", page_url: page.url || page.pageUrl, mode: "detail", detail };
  } else {
    if (!page.jobs.length) {
      $("status").textContent = "Tidak ada lowongan untuk dikirim.";
      return;
    }
    body = { source: "jobstreet", page_url: page.pageUrl, mode: "cards", jobs: page.jobs };
  }
  $("status").textContent = "Mengirim...";
  const reply = await chrome.runtime.sendMessage({ type: "gawe-import", body });
  // A worker that dies mid-request replies with nothing; say so rather than
  // throwing on `reply.ok`.
  if (!reply) {
    $("status").textContent = "Tidak ada jawaban dari latar ekstensi. Coba lagi.";
    return;
  }
  $("status").textContent = reply.ok ? describe(reply.result) : reply.error;
}

void init();
