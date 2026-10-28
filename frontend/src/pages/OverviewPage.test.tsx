import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type { Overview } from "../app/apiClient";
import { OverviewPage } from "./OverviewPage";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return { ...actual, getOverview: vi.fn() };
});

function overview(overrides: Partial<Overview> = {}): Overview {
  return {
    counts: {
      eligible: 0,
      needs_review: 0,
      ineligible: 0,
      total_jobs: 0,
      documents_pending_review: 0,
    },
    next_action: { code: "upload_master_cv", target_route: "/master-cv" },
    consent_required: false,
    provider_configured: true,
    recent_activity: [],
    ...overrides,
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
          <OverviewPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.getOverview).mockResolvedValue(overview());
});

describe("OverviewPage", () => {
  it("welcomes a first-time user and names the single next step", async () => {
    renderPage();

    expect(await screen.findByText("Selamat datang di Gawe")).toBeTruthy();
    expect(await screen.findByText("Langkah berikutnya")).toBeTruthy();
    expect(screen.getAllByText("Simpan CV Utama").length).toBeGreaterThan(0);
    // Internal words never reach the home screen.
    expect(screen.queryByText(/next_action|master_cv/i)).toBeNull();
  });

  it("points at the action the backend asks for, not a guess", async () => {
    vi.mocked(api.getOverview).mockResolvedValue(
      overview({
        next_action: { code: "grant_consent", target_route: "/settings" },
        consent_required: true,
      }),
    );
    renderPage();

    expect(
      (await screen.findAllByText("Izinkan pengiriman data ke layanan AI")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Izin pengiriman data")).toBeTruthy();
  });

  it("shows a plain sentence instead of raw counts alone", async () => {
    vi.mocked(api.getOverview).mockResolvedValue(
      overview({
        counts: {
          eligible: 3,
          needs_review: 1,
          ineligible: 0,
          total_jobs: 4,
          documents_pending_review: 2,
        },
        next_action: { code: "review_documents", target_route: "/applications" },
      }),
    );
    renderPage();

    expect(await screen.findByText(/3 lowongan/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /2 dokumen menunggu/ })).toBeTruthy();
  });

  it("reports a load failure with a retry, never a blank page", async () => {
    vi.mocked(api.getOverview).mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findByText("Data belum bisa dimuat")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Coba lagi" })).toBeTruthy();
  });
});
