import { Alert, Badge, Button, Card, Group, PasswordInput, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  ApiError,
  getProviderSettings,
  testProviderConnection,
  updateProviderSettings,
  type ProviderSettingsView,
  type ProviderTestResult,
} from "../app/apiClient";

const ROLES = ["extract", "classify", "write", "review"] as const;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : "Terjadi kesalahan.";
}

/** Edits the endpoint, the models per role, and the key. D24. */
export function ProviderSettings() {
  const [loaded, setLoaded] = useState<ProviderSettingsView | null>(null);
  const [providerId, setProviderId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [test, setTest] = useState<ProviderTestResult | null>(null);

  function apply(data: ProviderSettingsView) {
    setLoaded(data);
    setProviderId(data.provider_id ?? "");
    setBaseUrl(data.base_url ?? "");
    setModels(
      Object.fromEntries(ROLES.map((role) => [role, data.roles[role]?.model ?? ""])),
    );
  }

  useEffect(() => {
    let alive = true;
    getProviderSettings()
      .then((data) => {
        if (alive) apply(data);
      })
      .catch((error) => {
        if (alive) setFailure(errorMessage(error));
      });
    return () => {
      alive = false;
    };
  }, []);

  async function save() {
    setBusy(true);
    setFailure(null);
    setSaved(null);
    setTest(null);
    try {
      const data = await updateProviderSettings({
        provider_id: providerId.trim(),
        base_url: baseUrl.trim(),
        // The form no longer shows the models, so it sends back what config has.
        roles: Object.fromEntries(
          ROLES.map((role) => [role, (models[role] ?? "").trim()]),
        ),
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      });
      apply(data);
      setApiKey("");
      setSaved("Tersimpan. Consent mungkin perlu diperbarui bila model berubah.");
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    setBusy(true);
    setFailure(null);
    setTest(null);
    try {
      setTest(await testProviderConnection());
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const keyLabel =
    loaded?.key_source === "keyring"
      ? "tersimpan di keyring"
      : loaded?.key_source === "env"
        ? "dari environment"
        : "belum ada";

  return (
    <Card withBorder>
      <Group justify="space-between">
        <Text fw={500}>Provider LLM</Text>
        <Badge variant="light" color={loaded?.configured ? "green" : "orange"}>
          {loaded?.configured ? "configured" : "missing"}
        </Badge>
      </Group>
      <Text size="sm" c="dimmed" mt={4}>
        Endpoint diubah di sini; model per role memakai nilai yang sudah ada di
        config lokal. API key disimpan di Windows Credential Manager dan tidak
        pernah ditampilkan kembali.
      </Text>

      <Stack gap="xs" mt="sm">
        <Group grow align="end">
          <TextInput
            label="Nama provider"
            value={providerId}
            onChange={(event) => setProviderId(event.currentTarget.value)}
            placeholder="router"
          />
          <TextInput
            label="Base URL"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.currentTarget.value)}
            placeholder="https://contoh.example/v1"
          />
        </Group>

        <PasswordInput
          label={`API key (${keyLabel})`}
          description="Kosongkan bila tidak ingin mengganti key yang tersimpan."
          value={apiKey}
          onChange={(event) => setApiKey(event.currentTarget.value)}
          autoComplete="new-password"
        />
        {loaded && !loaded.key_writable ? (
          <Alert color="orange">
            Keyring tidak tersedia; key tidak dapat disimpan dari browser. Pakai
            variabel environment GAWE_LLM_API_KEY.
          </Alert>
        ) : null}

        <Group>
          <Button loading={busy} onClick={() => void save()}>
            Simpan
          </Button>
          <Button variant="light" loading={busy} onClick={() => void runTest()}>
            Test koneksi
          </Button>
        </Group>

        {saved ? <Alert color="teal">{saved}</Alert> : null}
        {failure ? <Alert color="red">{failure}</Alert> : null}
        {test ? (
          <Alert color="teal" title={`Tersambung dalam ${test.latency_ms} ms`}>
            <Text size="sm">
              {test.model_count} model tersedia
              {test.models.length
                ? `, contoh: ${test.models.slice(0, 5).join(", ")}`
                : "."}
            </Text>
            <Text size="xs" c="dimmed">
              Key dibaca dari {test.key_source}. Tidak ada data kandidat yang dikirim.
            </Text>
          </Alert>
        ) : null}
      </Stack>
    </Card>
  );
}
