import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type { MatchDetail, MatchItem, MatchList, Overview } from "../app/apiClient";
import { MatchesPage } from "./MatchesPage";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    getOverview: vi.fn(),
    listMatches: vi.fn(),
    getMatch: vi.fn(),
    overrideMatchTier: vi.fn(),
  };
});

function overview(confirmed: boolean): Overview {
  return {
    profile: {
      profile_id: "prf_1",
      profile_version_id: "prf_1",
      master_cv_id: "mcv_1",
      version: 1,
      status: confirmed ? "confirmed" : "draft",
      active: confirmed,
      confirmed_at: confirmed ? "2026-10-20T00:00:00Z" : null,
      created_at: "2026-10-20T00:00:00Z",
    },
    counts: {
      eligible: 1,
      needs_review: 0,
      ineligible: 0,
      total_jobs: 1,
      documents_pending_review: 0,
    },
    next_action: { code: confirmed ? "run_discovery" : "confirm_profile" },
    consent_required: false,
    provider_configured: true,
    recent_activity: [],
  };
}

function item(): MatchItem {
  return {
    job: {
      job_id: "job_1",
      job_posting_version_id: "jpv_1",
      source_id: "src_1",
      company: "Acme",
      title: "Senior Backend Engineer",
      location: { raw: "Jakarta, Indonesia", is_remote: false },
      work_mode: "onsite",
      market: "indonesia",
      fetched_at: "2026-10-20T00:00:00Z",
      apply_url: "https://example.com/apply",
      apply_url_status: "available",
      priority_tier: "P4",
      priority_confidence: "high",
    },
    profile_version_id: "prf_1",
    eligibility: {
      assessment_id: "elig_1",
      status: "eligible",
      confidence: "high",
      reason_summary: "Semua persyaratan wajib terpenuhi.",
    },
    fit: {
      assessment_id: "fit_1",
      fit_score: 82,
      verdict: "strong",
      confidence: "high",
    },
    recommendation: "apply_now",
    status_outdated: false,
    application_id: null,
  };
}

function list(items: MatchItem[] = [item()], hasMore = false): MatchList {
  return {
    items,
    page: { limit: 25, next_cursor: hasMore ? "cursor_2" : null, has_more: hasMore },
    ranking: {
      ranking_run_id: "rank_1",
      sort: "ranking",
      primary: "fit_score_desc",
      tie_breaker: ["priority_tier", "posted_at_desc", "job_id"],
      tie_window: 0,
    },
    counts: { eligible: 1, needs_review: 0, ineligible: 0, hidden_by_min_fit_score: 0 },
  };
}

function detail(): MatchDetail {
  return {
    job_detail: {
      job: item().job,
      description_text: "Build payment services.",
      description_truncated: false,
      requirements: [
        { requirement_id: "req_1", kind: "must_have", text: "5+ years backend" },
      ],
      source: {
        source_id: "src_1",
        source_kind: "registry",
        company: "Acme",
        verification_status: "verified",
        access_method: "ats_api",
      },
    },
    eligibility: {
      assessment_id: "elig_1",
      job_id: "job_1",
      job_posting_version_id: "jpv_1",
      profile_version_id: "prf_1",
      status: "eligible",
      checks: [
        {
          requirement_id: "req_1",
          category: "experience",
          result: "met",
          job_quote: "5+ years backend",
          evidence_refs: ["exp_1"],
          reason: "Profil memenuhi syarat.",
        },
      ],
      confidence: "high",
      reason_summary: "Semua persyaratan wajib terpenuhi.",
      status_outdated: false,
      computed_at: "2026-10-20T00:00:00Z",
    },
    fit: {
      assessment_id: "fit_1",
      job_posting_version_id: "jpv_1",
      profile_version_id: "prf_1",
      fit_score: 82,
      verdict: "strong",
      confidence: "high",
      components: [
        { name: "must_coverage", weight: 0.6, value: 1, contribution: 0.6 },
      ],
      gaps: [],
      status_outdated: false,
      computed_at: "2026-10-20T00:00:00Z",
    },
    recommendation: "apply_now",
    status_outdated: false,
    application_id: null,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <MatchesPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.getOverview).mockResolvedValue(overview(true));
  vi.mocked(api.listMatches).mockResolvedValue(list());
  vi.mocked(api.getMatch).mockResolvedValue(detail());
  vi.mocked(api.overrideMatchTier).mockResolvedValue(item());
});

describe("MatchesPage", () => {
  it("locks matches until the profile is confirmed", async () => {
    vi.mocked(api.getOverview).mockResolvedValue(overview(false));
    renderPage();

    expect(await screen.findByText("Matches terkunci")).toBeTruthy();
    expect(screen.queryByText("Senior Backend Engineer")).toBeNull();
  });

  it("renders the ranked table and requests the selected eligibility filter", async () => {
    renderPage();

    expect(await screen.findByText("Eligible · ranked")).toBeTruthy();
    expect(screen.getByText("Senior Backend Engineer")).toBeTruthy();
    expect(screen.getByText("82 · strong")).toBeTruthy();
    expect(screen.getAllByText("P4 · Indonesia onsite").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText(/Needs review/));
    await waitFor(() =>
      expect(api.listMatches).toHaveBeenLastCalledWith(
        expect.objectContaining({ eligibility: "needs_review", cursor: null }),
      ),
    );
  });

  it("pages forward with the backend cursor", async () => {
    vi.mocked(api.listMatches).mockResolvedValue(list([item()], true));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Berikutnya" }));
    await waitFor(() =>
      expect(api.listMatches).toHaveBeenLastCalledWith(
        expect.objectContaining({ cursor: "cursor_2" }),
      ),
    );
  });

  it("opens the side panel and stores a tier correction", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("Senior Backend Engineer"));
    expect(await screen.findByText("Build payment services.")).toBeTruthy();
    expect(screen.getByText("Buka halaman lamaran resmi")).toBeTruthy();

    const drawer = within(screen.getByRole("dialog"));
    fireEvent.click(drawer.getByLabelText("Tier"));
    const options = await screen.findAllByText("P1 · Global onsite");
    fireEvent.click(options[options.length - 1]);
    fireEvent.change(drawer.getByLabelText("Alasan"), { target: { value: "Relokasi" } });
    fireEvent.click(drawer.getByRole("button", { name: "Simpan koreksi" }));

    await waitFor(() =>
      expect(api.overrideMatchTier).toHaveBeenCalledWith("job_1", {
        tier: "P1",
        reason: "Relokasi",
      }),
    );
  });

  it("shows an empty state when no match is returned", async () => {
    vi.mocked(api.listMatches).mockResolvedValue(list([]));
    renderPage();

    expect(await screen.findByText("Belum ada job match")).toBeTruthy();
  });
});
