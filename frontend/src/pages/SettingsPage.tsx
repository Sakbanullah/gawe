import { useState } from "react";
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Code,
  Group,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";

import { friendlyError } from "../app/errors";
import {
  useConsent,
  useGrantConsent,
  useImportToken,
  useOverview,
  useRevokeConsent,
} from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { ProviderSettings } from "../components/ProviderSettings";
import { SourceRegistry } from "../components/SourceRegistry";
import type { PageState } from "../components/states";

const DATA_CLASS_LABEL: Record<string, string> = {
  cv_text: "isi CV",
  job_description: "deskripsi lowongan",
  profile_slice: "sebagian data profil",
};

function dataClassList(classes: string[]): string {
  return classes.map((item) => DATA_CLASS_LABEL[item] ?? item).join(", ");
}

export function SettingsPage() {
  const overview = useOverview();
  const consent = useConsent();
  const grant = useGrantConsent();
  const revoke = useRevokeConsent();
  const importToken = useImportToken();
  const [accepted, setAccepted] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copyImportToken() {
    const token = importToken.data?.token;
    if (!token) return;
    await navigator.clipboard.writeText(token);
    setCopied(true);
  }

  const loading = overview.isPending || consent.isPending;
  const failed = overview.isError || consent.isError;
  const state: PageState = loading ? "loading" : failed ? "error" : "ready";
  const status = consent.data;
  const scope = status?.required_scope;
  const consentError = grant.error ?? revoke.error;

  return (
    <PageFrame
      eyebrow="Pengaturan"
      title="Pengaturan"
      description="Semua yang berhubungan dengan mesin AI, izin data, dan daftar perusahaan ada di sini. Kamu jarang perlu membukanya setelah semuanya siap."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void consent.refetch();
      }}
    >
      {overview.data ? (
        <Stack gap="lg">
          <Card withBorder>
            <Stack gap="md">
              <div>
                <Title order={3}>Izin mengirim data ke layanan AI</Title>
                <Text size="sm" c="dimmed">
                  Gawe memakai layanan AI untuk membaca CV dan menulis draf. Sebelum mengirim,
                  Gawe minta izinmu dulu. Kamu bisa mencabutnya kapan saja.
                </Text>
              </div>

              <Group gap="xs">
                <Badge color={status?.granted ? "teal" : status?.required ? "orange" : "gray"} variant="light">
                  {status?.granted
                    ? "Izin aktif"
                    : status?.required
                      ? "Izin belum diberikan"
                      : "Tidak diperlukan"}
                </Badge>
              </Group>

              {status?.provider_changed_since_consent || status?.model_changed_since_consent ? (
                <Alert color="orange" title="Izin perlu diperbarui">
                  Layanan AI yang dipakai sudah berubah sejak izin terakhir. Berikan izin baru
                  sebelum data dikirim lagi.
                </Alert>
              ) : null}

              {status?.required_text ? (
                <Accordion variant="contained">
                  <Accordion.Item value="text">
                    <Accordion.Control>Baca isi pernyataan izin</Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="xs">
                        <Textarea value={status.required_text.display_text} readOnly autosize minRows={4} maxRows={14} />
                        <Text size="xs" c="dimmed">
                          Versi {status.required_text.text_version}
                        </Text>
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              ) : null}

              {status?.granted && status.current ? (
                <Stack gap="sm">
                  <Stack gap={4}>
                    <Text size="sm">Diberikan {status.current.granted_at}.</Text>
                    <Text size="sm">
                      Layanan yang dipakai: <Code>{status.current.scope.provider_id}</Code>
                    </Text>
                    <Text size="sm">
                      Data yang dikirim: {dataClassList(status.current.scope.data_classes)}.
                    </Text>
                  </Stack>
                  <Button
                    variant="light"
                    color="red"
                    loading={revoke.isPending}
                    onClick={() => void revoke.mutate(status.current?.consent_id ?? "")}
                  >
                    Cabut izin
                  </Button>
                </Stack>
              ) : scope ? (
                <Stack gap="sm">
                  <Text size="sm">
                    Data yang akan dikirim: {dataClassList(scope.data_classes)}. Kamu bisa
                    mencabut izin ini kapan saja.
                  </Text>
                  <Checkbox
                    checked={accepted}
                    onChange={(event) => setAccepted(event.currentTarget.checked)}
                    label="Saya sudah membaca pernyataan di atas dan setuju."
                  />
                  <Button
                    disabled={!accepted || grant.isPending}
                    loading={grant.isPending}
                    onClick={() =>
                      void grant.mutate({
                        providerId: scope.provider_id,
                        dataClasses: scope.data_classes,
                      })
                    }
                  >
                    Beri izin
                  </Button>
                </Stack>
              ) : (
                <Text size="sm" c="dimmed">
                  Layanan AI yang dipakai saat ini tidak mengirim data ke luar komputer ini.
                </Text>
              )}

              {consentError ? (
                <Alert color="red" title="Belum berhasil">
                  {friendlyError(consentError)}
                </Alert>
              ) : null}

              {status?.history.length ? (
                <Accordion variant="contained">
                  <Accordion.Item value="history">
                    <Accordion.Control>Riwayat izin</Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="xs">
                        <Table>
                          <Table.Thead>
                            <Table.Tr>
                              <Table.Th>Diberikan</Table.Th>
                              <Table.Th>Layanan</Table.Th>
                              <Table.Th>Dicabut</Table.Th>
                            </Table.Tr>
                          </Table.Thead>
                          <Table.Tbody>
                            {status.history.map((record) => (
                              <Table.Tr key={record.consent_id}>
                                <Table.Td>{record.granted_at}</Table.Td>
                                <Table.Td>{record.scope.provider_id}</Table.Td>
                                <Table.Td>{record.revoked_at ?? "masih berlaku"}</Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                        {status.history_truncated ? (
                          <Text size="xs" c="dimmed">
                            Riwayat yang lebih lama tidak ditampilkan.
                          </Text>
                        ) : null}
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              ) : null}
            </Stack>
          </Card>

          <ProviderSettings />

          <SourceRegistry editable />

          <Card withBorder>
            <Stack gap="sm">
              <div>
                <Title order={3}>Ambil lowongan dari halaman yang sedang kamu buka</Title>
                <Text size="sm" c="dimmed">
                  Ada ekstensi browser kecil yang bisa membaca lowongan yang sedang tampil di
                  halaman, lalu mengirimnya ke Gawe. Tidak ada login yang disimpan dan tidak ada
                  halaman yang dibuka otomatis.
                </Text>
              </div>
              <Group gap="xs">
                <Button
                  variant="light"
                  loading={importToken.isPending}
                  onClick={() => importToken.mutate()}
                >
                  Buat kode sambungan
                </Button>
              </Group>
              {importToken.data ? (
                <Stack gap="xs">
                  <Text size="sm">
                    Tempel kode ini di jendela kecil ekstensi. Kode lama langsung tidak berlaku.
                  </Text>
                  <Code block>{importToken.data.token}</Code>
                  <Group>
                    <Button variant="light" onClick={() => void copyImportToken()}>
                      Salin kode
                    </Button>
                    {copied ? (
                      <Text size="sm" c="teal">
                        Tersalin.
                      </Text>
                    ) : null}
                  </Group>
                </Stack>
              ) : null}
              {importToken.error ? (
                <Alert color="red" title="Belum berhasil">
                  {friendlyError(importToken.error)}
                </Alert>
              ) : null}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="xs">
              <Title order={3}>Penyimpanan data</Title>
              <Text size="sm" c="dimmed">
                Semua data lamaranmu tersimpan di komputer ini. Berapa lama data disimpan belum
                ditetapkan, jadi untuk saat ini tidak ada penghapusan otomatis.
              </Text>
            </Stack>
          </Card>
        </Stack>
      ) : null}
    </PageFrame>
  );
}
