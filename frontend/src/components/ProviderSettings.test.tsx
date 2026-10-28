import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../app/apiClient";
import { ProviderSettings } from "./ProviderSettings";

vi.mock("../app/apiClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../app/apiClient")>();
  return {
    ...actual,
    getProviderSettings: vi.fn(),
    updateProviderSettings: vi.fn(),
    testProviderConnection: vi.fn(),
  };
});

const settings: api.ProviderSettingsView = {
  provider_id: "router",
  configured: true,
  base_url: "https://router.example/v1",
  roles: {
    extract: { model: "model-x" },
    classify: { model: "model-y" },
    write: { model: "model-z" },
    review: { model: "model-w" },
  },
  key_source: "keyring",
  key_writable: true,
  providers: ["router"],
};

function renderCard() {
  return render(
    <MantineProvider>
      <ProviderSettings />
    </MantineProvider>,
  );
}

describe("ProviderSettings", () => {
  beforeEach(() => {
    vi.mocked(api.getProviderSettings).mockResolvedValue(settings);
    vi.mocked(api.updateProviderSettings).mockResolvedValue(settings);
    vi.mocked(api.testProviderConnection).mockResolvedValue({
      ok: true,
      latency_ms: 42,
      model_count: 2,
      models: ["model-a", "model-b"],
      key_source: "keyring",
    });
  });

  it("loads the saved endpoint and models", async () => {
    renderCard();
    await waitFor(() =>
      expect(screen.queryByDisplayValue("https://router.example/v1")).not.toBeNull(),
    );
    expect(screen.queryByText("Sudah siap")).not.toBeNull();
  });

  it("saves an edited endpoint without sending an empty key", async () => {
    renderCard();
    const url = await screen.findByDisplayValue("https://router.example/v1");
    fireEvent.change(url, { target: { value: "https://router2.example/v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Simpan" }));

    await waitFor(() => expect(api.updateProviderSettings).toHaveBeenCalled());
    const body = vi.mocked(api.updateProviderSettings).mock.calls[0][0];
    expect(body.base_url).toBe("https://router2.example/v1");
    expect(body.api_key).toBeUndefined();
    expect(body.roles).toEqual({
      extract: "model-x",
      classify: "model-y",
      write: "model-z",
      review: "model-w",
    });
  });

  it("does not render model fields", async () => {
    renderCard();
    await screen.findByDisplayValue("https://router.example/v1");
    expect(screen.queryByLabelText(/Extract/)).toBeNull();
    expect(screen.queryByLabelText(/Review/)).toBeNull();
  });

  it("sends the typed key when one is entered", async () => {
    renderCard();
    await screen.findByDisplayValue("https://router.example/v1");
    fireEvent.change(screen.getByLabelText(/Kunci akses/), { target: { value: "sk-new" } });
    fireEvent.click(screen.getByRole("button", { name: "Simpan" }));

    await waitFor(() => expect(api.updateProviderSettings).toHaveBeenCalled());
    expect(vi.mocked(api.updateProviderSettings).mock.calls[0][0].api_key).toBe("sk-new");
  });

  it("shows the connection test result", async () => {
    renderCard();
    await screen.findByDisplayValue("https://router.example/v1");
    fireEvent.click(screen.getByRole("button", { name: "Coba sambungan" }));

    await waitFor(() => expect(screen.queryByText(/Tersambung dalam 42 milidetik/)).not.toBeNull());
    expect(screen.queryByText(/model-a, model-b/)).not.toBeNull();
  });

  it("shows a readable error when the endpoint is rejected", async () => {
    vi.mocked(api.updateProviderSettings).mockRejectedValue(
      new api.ApiError(400, "invalid_base_url", "Endpoint harus URL https lengkap."),
    );
    renderCard();
    await screen.findByDisplayValue("https://router.example/v1");
    fireEvent.click(screen.getByRole("button", { name: "Simpan" }));

    await waitFor(() =>
      expect(screen.queryByText(/Alamat layanan AI harus diawali https/)).not.toBeNull(),
    );
  });

  it("warns when the keyring cannot store a key", async () => {
    vi.mocked(api.getProviderSettings).mockResolvedValue({
      ...settings,
      key_source: "missing",
      key_writable: false,
    });
    renderCard();
    await waitFor(() =>
      expect(screen.queryByText(/Kunci belum bisa disimpan dari sini/)).not.toBeNull(),
    );
  });
});

