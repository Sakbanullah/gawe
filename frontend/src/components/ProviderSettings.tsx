import { Alert, Badge, Button, Card, Group, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useEffect, useState } from "react";

import {
  getProviderSettings,
  testProviderConnection,
  updateProviderSettings,
  type ProviderSettingsView,
  type ProviderTestResult,
} from "../app/apiClient";
import { friendlyError } from "../app/errors";

const ROLES = ["extract", "classify", "write", "review"] as const;

/**
 * Edits the endpoint, the models per role, and the key (D24). Kept in an
 * accordion on the settings page: it is set once, not every day.
 */
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
    setModels(Object.fromEntries(ROLES.map((role) => [role, data.roles[role]?.model ?? ""])));
  }

  useEffect(() => {
    let alive = true;
    getProviderSettings()
      .then((data) => {
        if (alive) apply(data);
      })
      .catch((error) => {
        if (alive) setFailure(friendlyError(error, "Pengaturan layanan AI belum bisa dimuat."));
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
        roles: Object.fromEntries(ROLES.map((role) => [role, (models[role] ?? "").trim()])),
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      });
      apply(data);
      setApiKey("");
      setSaved("Tersimpan. Kalau layanan atau modelnya berubah, izin data mungkin perlu diperbarui.");
    } catch (error) {
      setFailure(friendlyError(error));
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
      setFailure(friendlyError(error, "Layanan AI belum bisa dihubungi."));
    } finally {
      setBusy(false);
    }
  }

  const keyLabel =
    loaded?.key_source === "keyring"
      ? "tersimpan di Windows"
      : loaded?.key_source === "env"
        ? "dari pengaturan sistem"
        : "belum ada";

  return (
    <Card withBorder>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <div>
            <Title order={3}>Layanan AI</Title>
            <Text size="sm" c="dimmed">
              Gawe memakai satu layanan AI untuk membaca CV dan menulis draf. Isi sekali saja.
            </Text>
          </div>
          <Badge color={loaded?.configured ? "teal" : "orange"} variant="light">
            {loaded?.configured ? "Sudah siap" : "Belum diisi"}
          </Badge>
        </Group>

        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            Kunci akses disimpan di Windows Credential Manager dan tidak pernah ditampilkan kembali.
          </Text>

          <Group grow align="flex-start">
            <TextInput
              label="Nama layanan"
              description="Nama pendek, misalnya router."
              value={providerId}
              onChange={(event) => setProviderId(event.currentTarget.value)}
              placeholder="router"
            />
            <TextInput
              label="Alamat layanan"
              description="Diawali https://"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.currentTarget.value)}
              placeholder="https://contoh.example/v1"
            />
          </Group>

          <PasswordInput
            label={`Kunci akses (${keyLabel})`}
            description="Kosongkan kalau tidak ingin mengganti kunci yang sudah tersimpan."
            value={apiKey}
            onChange={(event) => setApiKey(event.currentTarget.value)}
            autoComplete="new-password"
          />
          {loaded && !loaded.key_writable ? (
            <Alert color="orange" title="Kunci belum bisa disimpan dari sini">
              Penyimpanan kunci di Windows tidak tersedia. Isi kunci lewat pengaturan sistem
              dengan nama GAWE_LLM_API_KEY.
            </Alert>
          ) : null}

          <Group>
            <Button loading={busy} onClick={() => void save()}>
              Simpan
            </Button>
            <Button variant="light" loading={busy} onClick={() => void runTest()}>
              Coba sambungan
            </Button>
          </Group>

          {saved ? <Alert color="teal">{saved}</Alert> : null}
          {failure ? (
            <Alert color="red" title="Belum berhasil">
              {failure}
            </Alert>
          ) : null}
          {test ? (
            <Alert color="teal" title={`Tersambung dalam ${test.latency_ms} milidetik`}>
              <Text size="sm">
                {test.model_count} model tersedia
                {test.models.length ? `, contoh: ${test.models.slice(0, 3).join(", ")}` : "."}
              </Text>
              <Text size="xs" c="dimmed">
                Tidak ada data CV yang dikirim saat pengujian ini.
              </Text>
            </Alert>
          ) : null}
        </Stack>
      </Stack>
    </Card>
  );
}
