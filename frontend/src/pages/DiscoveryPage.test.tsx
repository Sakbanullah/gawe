import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type { DiscoveryRun, Overview, SourceRegistryEntry, Task } from "../app/apiClient";
import { DiscoveryPage } from "./DiscoveryPage";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    getOverview: vi.fn(),
    listSources: vi.fn(),
    listDiscoveryRuns: vi.fn(),
    getTask: vi.fn(),
    startDiscoveryRun: vi.fn(),
    retryTask: vi.fn(),
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
      eligible: 0,
      needs_review: 0,
      ineligible: 0,
      total_jobs: 0,
      documents_pending_review: 0,
    },
    next_action: { code: confirmed ? "run_discovery" : "confirm_profile" },
    consent_required: false,
    provider_configured: true,
    recent_activity: [],
  };
}

function source(): SourceRegistryEntry {
  return {
    source_id: "src_1",
    company: "Acme",
    market: "global",
    careers_url: "https://boards.greenhouse.io/acme",
    access_method: "ats_api",
    ats: "greenhouse",
    verification_status: "verified",
    tos_notes: null,
    last_checked_at: "2026-10-20T00:00:00Z",
    last_success_at: "2026-10-20T00:00:00Z",
    health_status: "healthy",
    consecutive_failures: 0,
    last_error_code: null,
    next_run_at: "2026-10-20T06:00:00Z",
    priority_order: 100,
    fetch_interval_minutes: 360,
    daily_request_quota: 24,
    requests_last_24h: 1,
    stale: false,
    enabled: true,
    job_count: 2,
    created_at: "2026-10-19T00:00:00Z",
    updated_at: "2026-10-20T00:00:00Z",
  };
}

function run(status: DiscoveryRun["status"] = "partial"): DiscoveryRun {
  return {
    run_id: "run_1",
    task_id: "tsk_1",
    status,
    profile_version_id: "prf_1",
    sources: [
      {
        source_id: "src_1",
        company: "Acme",
        status: "completed",
        fetched_count: 2,
        accepted_count: 2,
        duplicate_count: 0,
        retry_count: 0,
        stats: { skipped: 0, invalid: 0, truncated: 0, stale: 0 },
        last_attempt_at: "2026-10-20T00:00:00Z",
        error: null,
      },
      {
        source_id: "src_2",
        company: "Beta",
        status: "failed",
        fetched_count: 0,
        accepted_count: 0,
        duplicate_count: 0,
        retry_count: 0,
        last_attempt_at: "2026-10-20T00:00:00Z",
        error: {
          code: "source_unavailable",
          message: "Sumber tidak dapat dihubungi.",
          stage: "fetch",
          retryable: true,
          run_id: "run_1",
          request_id: null,
          details: [],
        },
      },
    ],
    counts: { fetched: 2, new_jobs: 2, duplicates: 0 },
    started_at: "2026-10-20T00:00:00Z",
    finished_at: "2026-10-20T00:00:01Z",
    error: null,
  };
}

function task(retryable: boolean): Task {
  return {
    task_id: "tsk_1",
    type: "discovery",
    status: "partial",
    application_id: null,
    progress: {
      current_stage: "fetch",
      completed_units: 1,
      total_units: 1,
      percent: 100,
      stages: [{ name: "fetch", status: "completed" }],
    },
    sources: [],
    retry: {
      retryable,
      attempt: 1,
      max_attempts: 3,
      retry_after_seconds: null,
      retried_from_task_id: null,
    },
    result: null,
    error: null,
    created_at: "2026-10-20T00:00:00Z",
    updated_at: "2026-10-20T00:00:01Z",
    finished_at: "2026-10-20T00:00:01Z",
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
          <DiscoveryPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.getOverview).mockResolvedValue(overview(true));
  vi.mocked(api.listSources).mockResolvedValue({
    items: [source()],
    page: { limit: 200, next_cursor: null, has_more: false },
  });
  vi.mocked(api.listDiscoveryRuns).mockResolvedValue({
    items: [],
    page: { limit: 10, next_cursor: null, has_more: false },
  });
  vi.mocked(api.getTask).mockResolvedValue(task(true));
  vi.mocked(api.startDiscoveryRun).mockResolvedValue({
    task_id: "tsk_2",
    type: "discovery",
    status: "processing",
    application_id: null,
    run_id: "run_2",
    extraction_run_id: null,
  });
  vi.mocked(api.retryTask).mockResolvedValue({
    task_id: "tsk_3",
    type: "discovery",
    status: "processing",
    application_id: null,
    run_id: "run_3",
    extraction_run_id: null,
  });
});

describe("DiscoveryPage", () => {
  it("locks discovery until the profile is confirmed", async () => {
    vi.mocked(api.getOverview).mockResolvedValue(overview(false));
    renderPage();

    expect(await screen.findByText("Discovery terkunci")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Buka Master CV" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Jalankan discovery" })).toBeNull();
  });

  it("starts a run when a verified source is enabled", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Jalankan discovery" }));
    await waitFor(() => expect(api.startDiscoveryRun).toHaveBeenCalledTimes(1));
  });

  it("shows per-source status and retries failed sources", async () => {
    vi.mocked(api.listDiscoveryRuns).mockResolvedValue({
      items: [run()],
      page: { limit: 10, next_cursor: null, has_more: false },
    });
    renderPage();

    expect(await screen.findByText("Hasil sebagian")).toBeTruthy();
    expect(screen.getByText("Sumber tidak dapat dihubungi.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ulangi sumber gagal" }));
    await waitFor(() =>
      expect(api.retryTask).toHaveBeenCalledWith("tsk_1", "failed_sources"),
    );
  });

  it("hides retry when no failed source is retryable", async () => {
    vi.mocked(api.listDiscoveryRuns).mockResolvedValue({
      items: [run()],
      page: { limit: 10, next_cursor: null, has_more: false },
    });
    vi.mocked(api.getTask).mockResolvedValue(task(false));
    renderPage();

    expect(await screen.findByText("Hasil sebagian")).toBeTruthy();
    await waitFor(() => expect(api.getTask).toHaveBeenCalledWith("tsk_1"));
    expect(screen.queryByRole("button", { name: "Ulangi sumber gagal" })).toBeNull();
  });

  it("warns when a source returned truncated or dropped records", async () => {
    const withStats = run("completed");
    withStats.sources[0].stats = { skipped: 1, invalid: 0, truncated: 2, stale: 0 };
    vi.mocked(api.listDiscoveryRuns).mockResolvedValue({
      items: [withStats],
      page: { limit: 10, next_cursor: null, has_more: false },
    });
    renderPage();

    expect(await screen.findByText("Data sumber tidak lengkap")).toBeTruthy();
    expect(
      screen.getByText("Acme: 2 deskripsi dipotong · 1 record dilewati"),
    ).toBeTruthy();
  });

  it("surfaces an assessment failure instead of reporting a clean run", async () => {
    const failedAssess = run("partial");
    failedAssess.sources = [failedAssess.sources[0]];
    failedAssess.error = {
      code: "assessment_failed",
      message: "Lowongan tersimpan tetapi analisis eligibility/fit gagal.",
      stage: "eligibility",
      retryable: false,
      run_id: "run_1",
      request_id: null,
      details: [],
    };
    vi.mocked(api.listDiscoveryRuns).mockResolvedValue({
      items: [failedAssess],
      page: { limit: 10, next_cursor: null, has_more: false },
    });
    renderPage();

    expect(await screen.findByText("Analisis tidak selesai")).toBeTruthy();
    expect(
      screen.getByText("Lowongan tersimpan tetapi analisis eligibility/fit gagal."),
    ).toBeTruthy();
  });
});
