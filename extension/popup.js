"use strict";

/**
 * Popup: reads the visible cards, sends them once, prints the counts.
 *
 * Nothing here paginates. The user moves to the next page in their own browser;
 * that keeps the traffic indistinguishable from a person browsing.
 *
 * On a job page the same button sends the full description for that one job,
 * keyed by the URL it already had from the search page. The backend replaces the
 * snippet and re-assesses, so the job stays one row and not two.
 */

const $ = (id) => document.getElementById(id);
const CONTENT_SCRIPT = "content/jobstreet.js";

function describe(result) {
  const lines = [];
  if (result.mode === "detail") {
    lines.push(result.accepted ? "Deskripsi penuh terkirim." : "Tidak ada yang diperbarui.");
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
  if (page.kind === "detail") {
    const detail = page.detail;
    if (!detail || !detail.description) {
      $("summary").textContent =
        "Deskripsi lowongan tidak ditemukan di halaman ini. Buka halaman detailnya dulu.";
      return;
    }
    const warning = likelyMissingRequirements(detail.description)
      ? " Deskripsi ini belum memuat bagian persyaratan."
      : "";
    $("summary").textContent = `Detail: ${detail.title}.${warning}`;
    $("send").textContent = "Kirim deskripsi penuh";
    $("send").disabled = false;
    return;
  }
  $("summary").textContent = `Terdeteksi ${page.jobs.length} lowongan di halaman ini.`;
  $("send").disabled = page.jobs.length === 0;
}

$("save").addEventListener("click", async () => {
  const token = $("token").value.trim();
  await chrome.storage.local.set({ token });
  $("status").textContent = token ? "Token disimpan." : "Token dikosongkan.";
});

$("send").addEventListener("click", async () => {
  const page = await readPage();
  let body;
  if (page.kind === "detail") {
    if (!page.detail || !page.detail.description) {
      $("status").textContent = "Deskripsi lowongan tidak ditemukan di halaman ini.";
      return;
    }
    body = { source: "jobstreet", page_url: page.pageUrl, mode: "detail", detail: page.detail };
  } else {
    if (!page.jobs.length) {
      $("status").textContent = "Tidak ada lowongan untuk dikirim.";
      return;
    }
    body = { source: "jobstreet", page_url: page.pageUrl, mode: "cards", jobs: page.jobs };
  }
  $("status").textContent = "Mengirim...";
  const reply = await chrome.runtime.sendMessage({ type: "gawe-import", body });
  $("status").textContent = reply.ok ? describe(reply.result) : reply.error;
});

void init();
