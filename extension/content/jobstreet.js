"use strict";

/**
 * Reads job data from a Jobstreet page the user opened.
 *
 * Two modes, both read-only: it never scrolls, clicks, or navigates. Everything
 * it returns is text the user can already see, so the page is loaded by the
 * user's browser and never by an automated one.
 *
 * Both are read on every page, because Jobstreet's split view shows the card
 * list and a job detail side by side:
 *
 * - `jobs`   — one record per job card, snippet only.
 * - `detail` — full description, company, location, posted date, or null.
 *
 * The popup injects this file every time it opens (`chrome.scripting`
 * re-runs a file rather than caching it), so everything lives inside one IIFE
 * that bails out when an earlier copy already installed the reader. Without it
 * the second injection throws "Identifier 'SEL' has already been declared".
 */

if (!window.gaweReadJobstreet) {
  (() => {
    const SEL = {
      card: "article[data-automation='normalJob'], article[data-testid='job-card']",
      title: "[data-automation='jobTitle'], a[data-automation='jobTitle']",
      company: "[data-automation='jobCompany'], [data-testid='company-name']",
      location: "[data-automation='jobLocation'], [data-testid='job-location']",
      salary: "[data-automation='jobSalary'], [data-testid='job-salary']",
      snippet: "[data-automation='jobShortDescription'], [data-testid='job-snippet']",
      posted: "[data-automation='jobListingDate'], [data-testid='job-detail-date']",
      detailCompany: "[data-automation='advertiser-name'], [data-testid='advertiser-name']",
      detailTitle: "h1",
      detailLocation: "[data-automation='job-detail-location'], [data-testid='job-detail-location']",
      description: "[data-automation='jobAdDetails'], [data-testid='jobAdDetails']",
    };

    const MAX_JOBS = 50;

    function text(node) {
      return node ? node.textContent.replace(/\s+/g, " ").trim() : null;
    }

    function absolute(href) {
      if (!href) return null;
      try {
        const url = new URL(href, window.location.origin);
        url.hash = "";
        for (const key of [...url.searchParams.keys()]) {
          if (key.startsWith("tracking") || key === "ref" || key === "src") {
            url.searchParams.delete(key);
          }
        }
        // Jobstreet serves the same posting under different slugs; the numeric
        // id in the path is the identity, so keep only that.
        const id = url.pathname.match(/\/(?:job|jobs)\/(?:[^/]*?-)?(\d{6,})\/?$/);
        if (id) url.pathname = `/job/${id[1]}`;
        return url.toString();
      } catch {
        return null;
      }
    }

    /** `30/10/2026` or `30 Oct 2026` -> ISO date. Anything else stays null. */
    function isoDate(raw) {
      if (!raw) return null;
      const trimmed = raw.trim();
      const dmy = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
      if (dmy) {
        const [, day, month, year] = dmy;
        return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
      }
      const parsed = new Date(trimmed);
      if (Number.isNaN(parsed.getTime())) return null;
      return parsed.toISOString().slice(0, 10);
    }

    /** Jobstreet often writes "30d ago" instead of a date. */
    function relativeDate(raw) {
      if (!raw) return null;
      const match = raw.trim().match(/^(\d+)\s*(d|h|m)\s+ago$/i);
      if (!match) return null;
      const value = Number(match[1]);
      const unit = match[2].toLowerCase();
      const millis = unit === "d" ? 86400000 : unit === "h" ? 3600000 : 60000;
      return new Date(Date.now() - value * millis).toISOString().slice(0, 10);
    }

    function postedAt(node) {
      const raw = text(node);
      return isoDate(raw) || relativeDate(raw);
    }

    function pageKind() {
      if (!/^id\.jobstreet\.com$/.test(window.location.hostname)) return "wrong-host";
      if (/\/job\//.test(window.location.pathname)) return "detail";
      if (/jobs/.test(window.location.pathname)) return "search";
      return "wrong-page";
    }

    function readCards() {
      const cards = [];
      for (const card of document.querySelectorAll(SEL.card)) {
        const link = card.querySelector(SEL.title);
        const url = absolute(link ? link.getAttribute("href") : null);
        const title = text(link);
        if (!url || !title) continue;
        cards.push({
          title,
          url,
          company: text(card.querySelector(SEL.company)),
          location: text(card.querySelector(SEL.location)),
          salary: text(card.querySelector(SEL.salary)),
          snippet: text(card.querySelector(SEL.snippet)),
          posted_at: postedAt(card.querySelector(SEL.posted)),
        });
        if (cards.length >= MAX_JOBS) break;
      }
      return cards;
    }

    /**
     * Nearest ancestor of the description that also holds a heading. On a split
     * view the first `h1` on the page is the search header, so the title has to
     * come from the detail panel, not from the document.
     */
    function detailScope(body) {
      let node = body.parentElement;
      while (node && node !== document.documentElement) {
        if (node.querySelector(SEL.detailTitle)) return node;
        node = node.parentElement;
      }
      return null;
    }

    function scopeTitle(scope) {
      for (const node of scope.querySelectorAll(SEL.detailTitle)) {
        if (!node.closest(SEL.card)) return text(node);
      }
      return null;
    }

    function readDetail() {
      const body = document.querySelector(SEL.description);
      if (!body) return null;
      const scope = detailScope(body);
      const title = scope ? scopeTitle(scope) : null;
      const url = absolute(window.location.toString());
      if (!title || !url) return null;
      // One line per block, so headings survive and the section splitter can
      // still find "Requirements".
      const description =
        Array.from(body.children)
          .map((node) => text(node))
          .filter(Boolean)
          .join("\n") || null;
      return {
        title,
        url,
        company: text(scope.querySelector(SEL.detailCompany)),
        location: text(scope.querySelector(SEL.detailLocation)),
        posted_at: postedAt(scope.querySelector(SEL.posted)),
        description,
      };
    }

    window.gaweReadJobstreet = () => {
      const kind = pageKind();
      // `pageUrl` is the report; `url` is the identity. Query noise (search
      // tracking, `?type=standard`) is dropped so the detail import lands on the
      // row the card import created instead of a second one.
      const pageUrl = window.location.toString();
      // `kind` only decides which page this is; both payloads are read whenever
      // the page shows them, so the split view can offer both imports.
      return {
        kind,
        pageUrl,
        url: absolute(pageUrl),
        pageTitle: document.title,
        jobs: kind === "wrong-host" ? [] : readCards(),
        detail: kind === "wrong-host" ? null : readDetail(),
      };
    };
  })();
}
