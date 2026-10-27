import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type {
  ApplicationList,
  ApplicationWorkspace,
  DocumentSummary,
  DocumentVersion,
  ExportList,
  FindingsReport,
  Overview,
  TaskCreated,
} from "../app/apiClient";
import { ApplicationWorkspacePage } from "./ApplicationWorkspacePage";
import { ApplicationsPage } from "./ApplicationsPage";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    getOverview: vi.fn(),
    listApplications: vi.fn(),
    createApplicationFromUrl: vi.fn(),
    listExports: vi.fn(),
    createExport: vi.fn(),
    getApplication: vi.fn(),
    rerunApplicationAnalysis: vi.fn(),
    getDocumentVersion: vi.fn(),
    getDocumentFindings: vi.fn(),
    generateDocuments: vi.fn(),
    runDocumentReview: vi.fn(),
    approveDocumentVersion: vi.fn(),
    createDocumentRevision: vi.fn(),
  };
});

function overview(): Overview {
  return {
    profile: {
      profile_id: "prf_1",
      profile_version_id: "prf_1",
      master_cv_id: "mcv_1",
      version: 1,
      status: "confirmed",
      active: true,
      confirmed_at: "2026-10-20T00:00:00Z",
      created_at: "2026-10-20T00:00:00Z",
    },
    counts: {
      eligible: 1,
      needs_review: 0,
      ineligible: 0,
      total_jobs: 1,
      documents_pending_review: 0,
    },
    next_action: { code: "run_discovery" },
    consent_required: false,
    provider_configured: true,
    recent_activity: [],
  };
}

const JOB = {
  job_id: "job_1",
  job_posting_version_id: "jpv_1",
  source_id: "src_1",
  company: "Acme",
  title: "Senior Backend Engineer",
  location: { raw: "Jakarta, Indonesia" },
  work_mode: "onsite" as const,
  market: "indonesia" as const,
  fetched_at: "2026-10-20T00:00:00Z",
  apply_url: "https://example.com/apply",
  apply_url_status: "available" as const,
  priority_tier: "P4" as const,
  priority_confidence: "high" as const,
};

function applicationList(): ApplicationList {
  return {
    items: [
      {
        application_id: "app_1",
        job: JOB,
        status: "not_started",
        profile_version_id: "prf_1",
        eligibility_status: "eligible",
        fit_score: 82,
        document_counts: { cv_versions: 0, cover_letter_versions: 0, pending_review: 0 },
        created_at: "2026-10-20T00:00:00Z",
        updated_at: "2026-10-20T00:00:00Z",
      },
    ],
    page: { limit: 200, next_cursor: null, has_more: false },
  };
}

function workspace(overrides: Partial<ApplicationWorkspace> = {}): ApplicationWorkspace {
  return {
    application_id: "app_1",
    status: "not_started",
    job: JOB,
    job_posting_version_id: "jpv_1",
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
    documents: { cv: [], cover_letter: [] },
    suggested_filenames: {
      cv: "CV_Candidate_Acme_Senior_Backend_Engineer.pdf",
      cover_letter: "Cover_Letter_Candidate_Acme_Senior_Backend_Engineer.pdf",
    },
    next_action: {
      code: "review_documents",
      label: "Buat dokumen lamaran",
      reason: "Belum ada versi dokumen; pembuatan dokumen belum tersedia.",
    },
    active_task_id: null,
    created_at: "2026-10-20T00:00:00Z",
    updated_at: "2026-10-20T00:00:00Z",
    ...overrides,
  };
}

function documentSummary(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    document_version_id: "docv_1",
    application_id: "app_1",
    profile_version_id: "prf_1",
    job_posting_version_id: "jpv_1",
    kind: "cv",
    version: 1,
    status: "draft",
    content_hash: "hash_1",
    review_status: "not_started",
    approved: false,
    exported: false,
    pdf_available: false,
    created_at: "2026-10-20T00:00:00Z",
    ...overrides,
  };
}

function documentVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    ...documentSummary(),
    content: {
      kind: "cv",
      header: { full_name: "Ayu Pratama", email: "ayu@example.com" },
      summary: { text: "Backend engineer." },
      skills: [{ name: "Python" }],
      experience: [
        {
          company: "Acme",
          title: "Senior Backend Engineer",
          start: "2022-07",
          end: null,
          bullets: [{ id: "b1", text: "Built payments." }],
        },
      ],
      missing: [],
    },
    diff: {
      base: "master_cv",
      items: [{ path: "experience.exp_1", change: "selected" }],
    },
    ...overrides,
  };
}

function findings(): FindingsReport {
  return {
    document_version_id: "docv_1",
    profile_version_id: "prf_1",
    review_run_id: "tsk_review",
    cycle: 1,
    verdict: "pass",
    findings: [],
    reviewed_at: "2026-10-20T00:00:00Z",
  };
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/applications/:id" element={<ApplicationWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.getOverview).mockResolvedValue(overview());
  vi.mocked(api.listApplications).mockResolvedValue(applicationList());
  vi.mocked(api.getApplication).mockResolvedValue(workspace());
  vi.mocked(api.rerunApplicationAnalysis).mockResolvedValue({
    task_id: "tsk_1",
    type: "analysis",
    status: "completed",
    application_id: "app_1",
  } as TaskCreated);
  vi.mocked(api.getDocumentVersion).mockResolvedValue(documentVersion());
  vi.mocked(api.getDocumentFindings).mockResolvedValue(findings());
  vi.mocked(api.generateDocuments).mockResolvedValue({
    task_id: "tsk_gen",
    type: "document_generation",
    status: "completed",
    application_id: "app_1",
  } as TaskCreated);
  vi.mocked(api.runDocumentReview).mockResolvedValue({
    task_id: "tsk_review",
    type: "review",
    status: "completed",
    application_id: "app_1",
  } as TaskCreated);
  vi.mocked(api.approveDocumentVersion).mockResolvedValue({
    approval_id: "apr_1",
    document_version_id: "docv_1",
    profile_version_id: "prf_1",
    document_hash: "hash_1",
    kind: "cv",
    decision: "approved",
    note: null,
    decided_at: "2026-10-20T00:00:00Z",
  });
  vi.mocked(api.createDocumentRevision).mockResolvedValue(
    documentVersion({ document_version_id: "docv_2", version: 2 }),
  );
  vi.mocked(api.createApplicationFromUrl).mockResolvedValue({
    application_id: "app_2",
    job_id: "job_2",
    task_id: "tsk_url",
    deduplicated: false,
  });
  vi.mocked(api.listExports).mockResolvedValue({
    application_id: "app_1",
    items: [],
    page: { limit: 200, next_cursor: null, has_more: false },
  } satisfies ExportList);
  vi.mocked(api.createExport).mockResolvedValue({
    task_id: "tsk_export",
    type: "export",
    status: "completed",
    application_id: "app_1",
  } as TaskCreated);
});

describe("ApplicationsPage", () => {
  it("lists workspaces with backend eligibility and fit", async () => {
    renderAt("/applications");

    expect(await screen.findByText("Senior Backend Engineer")).toBeTruthy();
    expect(screen.getByText("eligible")).toBeTruthy();
    expect(screen.getByText("Fit 82")).toBeTruthy();
    expect(screen.getByText("Not started")).toBeTruthy();
  });

  it("shows the empty state when no workspace exists", async () => {
    vi.mocked(api.listApplications).mockResolvedValue({
      items: [],
      page: { limit: 200, next_cursor: null, has_more: false },
    });
    renderAt("/applications");

    expect(await screen.findByText("Belum ada application.")).toBeTruthy();
  });

  it("creates a workspace from a pasted URL", async () => {
    renderAt("/applications");

    fireEvent.change(await screen.findByLabelText("Tambah dari URL lowongan"), {
      target: { value: "https://example.com/jobs/1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buat workspace" }));

    await waitFor(() =>
      expect(api.createApplicationFromUrl).toHaveBeenCalledWith(
        "https://example.com/jobs/1",
        undefined,
      ),
    );
  });

  it("sends pasted text when the page cannot be read", async () => {
    renderAt("/applications");

    fireEvent.change(await screen.findByLabelText("Tambah dari URL lowongan"), {
      target: { value: "https://example.com/jobs/1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Halaman tidak bisa dibaca? Tempel teksnya" }),
    );
    fireEvent.change(screen.getByLabelText("Teks lowongan"), {
      target: { value: "Senior Backend Engineer - Acme\n\nPython dan PostgreSQL." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buat workspace" }));

    await waitFor(() =>
      expect(api.createApplicationFromUrl).toHaveBeenCalledWith(
        "https://example.com/jobs/1",
        "Senior Backend Engineer - Acme\n\nPython dan PostgreSQL.",
      ),
    );
  });

  it.each([
    ["source_not_found", "Halaman lowongan tidak ditemukan"],
    ["manual_fetch_failed", "Halaman tidak bisa dibaca otomatis"],
    ["robots_disallowed", "robots.txt menolak pembacaan halaman"],
    ["manual_page_unreadable", "Isi halaman tidak terbaca"],
  ])("names the failure for %s and offers the textarea", async (code, title) => {
    vi.mocked(api.createApplicationFromUrl).mockRejectedValue(
      new api.ApiError(400, code, "Tempelkan teks lowongan secara manual."),
    );
    renderAt("/applications");

    fireEvent.change(await screen.findByLabelText("Tambah dari URL lowongan"), {
      target: { value: "https://example.com/jobs/1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buat workspace" }));

    expect(await screen.findByText(title)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tempel teks lowongan" }));
    expect(screen.getByLabelText("Teks lowongan")).toBeTruthy();
  });
});

describe("ApplicationWorkspacePage", () => {
  it("shows eligibility, fit, filenames, and the Apply link", async () => {
    renderAt("/applications/app_1");

    expect(await screen.findByText("Senior Backend Engineer · Acme")).toBeTruthy();
    expect(screen.getByText("Fit 82")).toBeTruthy();
    expect(
      screen.getByText("CV: CV_Candidate_Acme_Senior_Backend_Engineer.pdf"),
    ).toBeTruthy();
    expect(screen.getByText("Buka halaman lamaran resmi")).toBeTruthy();
    expect(
      screen.getByText("Belum ada versi dokumen. Buat draft saat eligibility eligible."),
    ).toBeTruthy();
  });

  it("blocks documents when eligibility needs review", async () => {
    vi.mocked(api.getApplication).mockResolvedValue(
      workspace({
        status: "needs_review",
        eligibility: {
          assessment_id: "elig_1",
          status: "needs_review",
          confidence: "medium",
          reason_summary: "Izin kerja belum jelas.",
        },
        fit: null,
        next_action: {
          code: "review_matches",
          label: "Tinjau requirement yang belum jelas",
          reason: "Eligibility needs_review memblokir pembuatan dokumen.",
        },
      }),
    );
    renderAt("/applications/app_1");

    expect(await screen.findByText("Dokumen diblokir")).toBeTruthy();
    expect(screen.getByText("Fit belum dihitung. Eligibility harus eligible lebih dulu.")).toBeTruthy();
  });

  it("requests an explicit re-analysis and never a silent one", async () => {
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Analisis ulang" }));
    await waitFor(() =>
      expect(api.rerunApplicationAnalysis).toHaveBeenCalledWith("app_1", {
        reason: "user_requested",
      }),
    );
  });

  it("generates a draft only when eligibility is eligible", async () => {
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Buat CV" }));
    await waitFor(() =>
      expect(api.generateDocuments).toHaveBeenCalledWith("app_1", {
        kinds: ["cv"],
        language: "en",
      }),
    );
  });

  it("sends only the cover letter when that button is used", async () => {
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Buat cover letter" }));
    await waitFor(() =>
      expect(api.generateDocuments).toHaveBeenCalledWith("app_1", {
        kinds: ["cover_letter"],
        language: "en",
      }),
    );
    expect(api.generateDocuments).toHaveBeenCalledTimes(1);
  });

  it("lists versions and shows the diff, review, and approval actions", async () => {
    vi.mocked(api.getApplication).mockResolvedValue(
      workspace({
        status: "in_review",
        documents: { cv: [documentSummary({ review_status: "completed", status: "in_review" })], cover_letter: [] },
      }),
    );
    vi.mocked(api.getDocumentVersion).mockResolvedValue(
      documentVersion({ review_status: "completed", status: "in_review" }),
    );
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Lihat" }));
    expect(await screen.findByText("CV v1")).toBeTruthy();
    expect(screen.getByText("Basis: Master CV")).toBeTruthy();
    expect(screen.getByText("experience.exp_1")).toBeTruthy();

    const approveButton = screen.getByRole("button", { name: "Setujui versi ini" });
    await waitFor(() => expect((approveButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(approveButton);
    await waitFor(() =>
      expect(api.approveDocumentVersion).toHaveBeenCalledWith("app_1", "docv_1", {
        decision: "approved",
        content_hash: "hash_1",
        note: "",
      }),
    );
  });

  it("runs review explicitly for a draft version", async () => {
    vi.mocked(api.getApplication).mockResolvedValue(
      workspace({ documents: { cv: [documentSummary()], cover_letter: [] } }),
    );
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Lihat" }));
    fireEvent.click(await screen.findByRole("button", { name: "Jalankan review" }));
    await waitFor(() =>
      expect(api.runDocumentReview).toHaveBeenCalledWith("app_1", "docv_1"),
    );
  });

  it("exports only an approved version and links the final PDF", async () => {
    vi.mocked(api.getApplication).mockResolvedValue(
      workspace({
        status: "approved",
        documents: {
          cv: [documentSummary({ status: "approved", review_status: "completed", approved: true })],
          cover_letter: [],
        },
      }),
    );
    vi.mocked(api.getDocumentVersion).mockResolvedValue(
      documentVersion({ status: "approved", review_status: "completed", approved: true }),
    );
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Lihat" }));
    const exportButton = await screen.findByRole("button", { name: "Ekspor PDF" });
    await waitFor(() => expect((exportButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(exportButton);

    await waitFor(() =>
      expect(api.createExport).toHaveBeenCalledWith("app_1", {
        kind: "cv",
        document_version_id: "docv_1",
        content_hash: "hash_1",
      }),
    );
    expect(screen.getByText("Preview PDF")).toBeTruthy();
  });

  it("marks information that the profile does not provide", async () => {
    vi.mocked(api.getApplication).mockResolvedValue(
      workspace({ documents: { cv: [documentSummary()], cover_letter: [] } }),
    );
    vi.mocked(api.getDocumentVersion).mockResolvedValue(
      documentVersion({
        content: {
          kind: "cv",
          header: { full_name: "Ayu Pratama" },
          summary: null,
          missing: ["personal.email", "summary"],
        },
      }),
    );
    renderAt("/applications/app_1");

    fireEvent.click(await screen.findByRole("button", { name: "Lihat" }));
    expect(await screen.findByText("Informasi belum tersedia")).toBeTruthy();
    expect(screen.getByText("personal.email, summary")).toBeTruthy();
  });
});
