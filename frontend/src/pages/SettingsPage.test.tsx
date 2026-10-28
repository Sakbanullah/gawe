import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type { ConsentRecord, ConsentStatus, Overview } from "../app/apiClient";
import { SettingsPage } from "./SettingsPage";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    getOverview: vi.fn(),
    getConsent: vi.fn(),
    grantConsent: vi.fn(),
    revokeConsent: vi.fn(),
    listSources: vi.fn(),
    createSource: vi.fn(),
    updateSource: vi.fn(),
    issueBrowserImportToken: vi.fn(),
  };
});

const REQUIRED_TEXT = {
  text_version: "2026-10-19.1",
  text_sha256: "a".repeat(64),
  display_text: "Teks consent uji.",
  issued_at: "2026-10-19T00:00:00Z",
};

const DATA_CLASSES = ["cv_text", "job_description", "profile_slice"] as const;

function record(overrides: Partial<ConsentRecord> = {}): ConsentRecord {
  return {
    consent_id: "consent_1",
    consent_type: "cloud_data_processing",
    scope: {
      data_classes: [...DATA_CLASSES],
      provider_id: "provider_a",
      model_roles: { extract: "model-x", write: "model-y" },
    },
    text_version: "2026-10-19.1",
    granted_at: "2026-10-19T00:00:00Z",
    revoked_at: null,
    ...overrides,
  };
}

function status(overrides: Partial<ConsentStatus> = {}): ConsentStatus {
  return {
    required: true,
    granted: false,
    current: null,
    required_scope: {
      data_classes: [...DATA_CLASSES],
      provider_id: "provider_a",
      model_roles: { extract: "model-x", write: "model-y" },
    },
    required_text: REQUIRED_TEXT,
    history: [],
    history_truncated: false,
    ...overrides,
  };
}

function overview(): Overview {
  return {
    counts: {
      eligible: 0,
      needs_review: 0,
      ineligible: 0,
      total_jobs: 0,
      documents_pending_review: 0,
    },
    next_action: { code: "none" },
    consent_required: true,
    provider_configured: true,
    recent_activity: [],
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

async function renderLoaded() {
  renderPage();
  await screen.findByText("Izin mengirim data ke layanan AI");
}

beforeEach(() => {
  vi.mocked(api.getOverview).mockResolvedValue(overview());
  vi.mocked(api.getConsent).mockResolvedValue(status());
  vi.mocked(api.grantConsent).mockResolvedValue(record());
  vi.mocked(api.revokeConsent).mockResolvedValue(
    record({ revoked_at: "2026-10-19T01:00:00Z" }),
  );
  vi.mocked(api.listSources).mockResolvedValue({
    items: [],
    page: { limit: 200, next_cursor: null, has_more: false },
  });
});

describe("SettingsPage consent", () => {
  it("shows the active consent, its scope, and the history", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({
        granted: true,
        required: false,
        current: record(),
        history: [
          record(),
          record({
            consent_id: "consent_0",
            granted_at: "2026-10-18T00:00:00Z",
            revoked_at: "2026-10-18T01:00:00Z",
          }),
        ],
      }),
    );

    await renderLoaded();

    expect(await screen.findByText("Izin aktif")).toBeTruthy();
    expect(screen.getByText("Cabut izin")).toBeTruthy();
    expect(screen.getByText(/Diberikan 2026-10-19T00:00:00Z/)).toBeTruthy();
    expect(screen.getAllByText("provider_a").length).toBeGreaterThan(0);

    // History is behind a disclosure so the common case stays short.
    expect(screen.queryByText("2026-10-18T01:00:00Z")).toBeNull();
    fireEvent.click(screen.getByText("Riwayat izin"));
    expect(await screen.findByText("2026-10-18T01:00:00Z")).toBeTruthy();
  });

  it("requires the checkbox before granting consent and sends the server scope", async () => {
    await renderLoaded();

    const checkbox = screen.getByLabelText(
      "Saya sudah membaca pernyataan di atas dan setuju.",
    );
    const button = screen.getByRole("button", { name: "Beri izin" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);

    fireEvent.click(checkbox);
    expect(button.disabled).toBe(false);
    fireEvent.click(button);

    await waitFor(() =>
      expect(api.grantConsent).toHaveBeenCalledWith({
        provider_id: "provider_a",
        data_classes: [...DATA_CLASSES],
      }),
    );
  });

  it("revokes the current consent by id", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({ granted: true, required: false, current: record() }),
    );

    await renderLoaded();
    fireEvent.click(await screen.findByRole("button", { name: "Cabut izin" }));

    await waitFor(() => expect(api.revokeConsent).toHaveBeenCalledWith("consent_1"));
  });

  it("warns when the provider changed since consent", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({
        granted: true,
        required: false,
        current: record(),
        provider_changed_since_consent: true,
      }),
    );

    await renderLoaded();
    expect(await screen.findByText("Izin perlu diperbarui")).toBeTruthy();
  });

  it("warns when a model changed since consent", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({
        granted: true,
        required: false,
        current: record(),
        model_changed_since_consent: true,
      }),
    );

    await renderLoaded();
    expect(await screen.findByText("Izin perlu diperbarui")).toBeTruthy();
  });

  it("reports a truncated history", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({ history: [record()], history_truncated: true }),
    );

    await renderLoaded();
    expect(await screen.findByText("Riwayat yang lebih lama tidak ditampilkan.")).toBeTruthy();
  });

  it("shows that consent is not required for a local provider", async () => {
    vi.mocked(api.getConsent).mockResolvedValue(
      status({ required: false, required_scope: null, required_text: undefined }),
    );

    await renderLoaded();
    expect(await screen.findByText("Tidak diperlukan")).toBeTruthy();
    expect(
      screen.getByText(/tidak mengirim data ke luar komputer ini/),
    ).toBeTruthy();
  });
});

describe("SettingsPage import token", () => {
  beforeEach(() => {
    vi.mocked(api.issueBrowserImportToken).mockClear();
  });

  it("issues a token only when the button is clicked", async () => {
    vi.mocked(api.issueBrowserImportToken).mockResolvedValue({
      token: "tok_1",
      header: "X-Gawe-Token",
    });

    await renderLoaded();

    // Opening Settings must not rotate the extension token. A query on this
    // endpoint would refetch on mount and on window focus, revoking the token
    // the user already pasted into the popup.
    expect(api.issueBrowserImportToken).not.toHaveBeenCalled();
    expect(screen.queryByText("tok_1")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Buat kode sambungan" }));

    expect(await screen.findByText("tok_1")).toBeTruthy();
    expect(api.issueBrowserImportToken).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Salin kode" })).toBeTruthy();
  });
});

