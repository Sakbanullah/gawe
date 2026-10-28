import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import type { SourceRegistryEntry } from "../app/apiClient";
import { SourceRegistry } from "./SourceRegistry";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    listSources: vi.fn(),
    createSource: vi.fn(),
    updateSource: vi.fn(),
  };
});

function source(overrides: Partial<SourceRegistryEntry> = {}): SourceRegistryEntry {
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
    job_count: 12,
    created_at: "2026-10-19T00:00:00Z",
    updated_at: "2026-10-20T00:00:00Z",
    ...overrides,
  };
}

function renderRegistry(editable = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <SourceRegistry editable={editable} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  vi.mocked(api.listSources).mockResolvedValue({
    items: [source()],
    page: { limit: 200, next_cursor: null, has_more: false },
  });
  vi.mocked(api.createSource).mockResolvedValue(source({ source_id: "src_new" }));
  vi.mocked(api.updateSource).mockResolvedValue(source({ enabled: false }));
});

describe("SourceRegistry", () => {
  it("shows verification status and last checked time", async () => {
    renderRegistry();
    expect(await screen.findByText("Acme")).toBeTruthy();
    expect(screen.getByText("Sudah dicek")).toBeTruthy();
    expect(screen.getByText("Ya")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("disables a source through the update endpoint", async () => {
    renderRegistry();
    fireEvent.click(await screen.findByRole("button", { name: "Jangan dicari" }));
    await waitFor(() =>
      expect(api.updateSource).toHaveBeenCalledWith("src_1", { enabled: false }),
    );
  });

  it("creates a new source as unverified and disabled", async () => {
    vi.mocked(api.listSources).mockResolvedValue({
      items: [],
      page: { limit: 200, next_cursor: null, has_more: false },
    });
    renderRegistry();

    fireEvent.change(await screen.findByLabelText("Nama perusahaan"), {
      target: { value: "Beta" },
    });
    fireEvent.change(screen.getByLabelText("Alamat halaman karier"), {
      target: { value: "https://jobs.lever.co/beta" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tambah perusahaan" }));

    await waitFor(() =>
      expect(api.createSource).toHaveBeenCalledWith({
        company: "Beta",
        careers_url: "https://jobs.lever.co/beta",
        market: "global",
        ats: "greenhouse",
        access_method: "ats_api",
        tos_notes: undefined,
        enabled: false,
        priority_order: 100,
        fetch_interval_minutes: 360,
        daily_request_quota: 24,
      }),
    );
  });

  it("edits a source from the modal", async () => {
    renderRegistry();
    fireEvent.click(await screen.findByRole("button", { name: "Ubah" }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Nama perusahaan"), {
      target: { value: "Acme Baru" },
    });
    fireEvent.change(within(dialog).getByLabelText("Alamat halaman karier"), {
      target: { value: "https://jobs.lever.co/acme" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Simpan perubahan" }));

    await waitFor(() =>
      expect(api.updateSource).toHaveBeenCalledWith(
        "src_1",
        expect.objectContaining({
          company: "Acme Baru",
          careers_url: "https://jobs.lever.co/acme",
          market: "global",
          ats: "greenhouse",
          verification_status: "verified",
        }),
      ),
    );
    // Unchanged, so not resent: a legacy row may still hold an access method the
    // request contract no longer accepts.
    expect(vi.mocked(api.updateSource).mock.calls[0][1]).not.toHaveProperty(
      "access_method",
    );
  });

  it("maps a field validation error and clears it when the input changes", async () => {
    vi.mocked(api.updateSource).mockRejectedValueOnce(
      new api.ApiError(400, "validation_failed", "Careers URL tidak cocok dengan ATS.", [
        {
          field: "careers_url",
          code: "ats_host_mismatch",
          message: "Host careers_url harus milik ATS yang dipilih.",
        },
      ]),
    );
    renderRegistry();
    fireEvent.click(await screen.findByRole("button", { name: "Ubah" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByLabelText("Alamat halaman karier")).toHaveLength(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "Simpan perubahan" }));
    // The field error is plain language and sits on the input that caused it.
    expect(
      await within(dialog).findByText(
        "Alamat halaman karier harus memakai domain penyedia lowongan yang dipilih.",
      ),
    ).toBeTruthy();
    // The request error itself stays generic: no raw server wording, no field name.
    expect(
      await within(dialog).findByText("Ada isian yang belum sesuai. Periksa lagi lalu simpan ulang."),
    ).toBeTruthy();
    expect(within(dialog).queryByText(/careers_url/)).toBeNull();

    const input = within(screen.getByRole("dialog")).getByLabelText(
      "Alamat halaman karier",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "https://boards.greenhouse.io/acme-2" } });
    expect(input.value).toBe("https://boards.greenhouse.io/acme-2");
    const refreshed = screen.getByRole("dialog");
    await waitFor(() =>
      expect(
        within(refreshed).queryByText(
          "Alamat halaman karier harus memakai domain penyedia lowongan yang dipilih.",
        ),
      ).toBeNull(),
    );
    expect(
      within(refreshed).queryByText("Ada isian yang belum sesuai. Periksa lagi lalu simpan ulang."),
    ).toBeNull();
  });

  it("hides management controls in read-only mode", async () => {
    renderRegistry(false);
    expect(await screen.findByText("Acme")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ubah" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Tambah perusahaan" })).toBeNull();
  });
});

