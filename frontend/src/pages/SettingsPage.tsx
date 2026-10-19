import { useState } from "react";
import {
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
} from "@mantine/core";

import { useConsent, useGrantConsent, useOverview, useRevokeConsent } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { SourceRegistry } from "../components/SourceRegistry";
import type { PageState } from "../components/states";

export function SettingsPage() {
  const overview = useOverview();
  const consent = useConsent();
  const grant = useGrantConsent();
  const revoke = useRevokeConsent();
  const [accepted, setAccepted] = useState(false);

  const loading = overview.isPending || consent.isPending;
  const failed = overview.isError || consent.isError;
  const state: PageState = loading ? "loading" : failed ? "error" : "ready";
  const status = consent.data;
  const scope = status?.required_scope;

  return (
    <PageFrame
      title="Settings"
      description="Provider, consent, preferensi, sumber, dan retensi sementara."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void consent.refetch();
      }}
    >
      {overview.data ? (
        <Stack gap="md">
          <Card withBorder>
            <Group justify="space-between">
              <Text fw={500}>Provider</Text>
              <Badge variant="light">
                {overview.data.provider_configured ? "configured" : "missing"}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Provider dan model per role dibaca dari config lokal. Tidak ada model default.
            </Text>
          </Card>

          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Text fw={500}>Consent</Text>
              <Badge variant="light" color={status?.granted ? "green" : "orange"}>
                {status?.granted ? "aktif" : status?.required ? "diperlukan" : "tidak diperlukan"}
              </Badge>
            </Group>

            {status?.provider_changed_since_consent || status?.model_changed_since_consent ? (
              <Alert color="orange" mb="xs" title="Consent perlu diperbarui">
                Provider atau model berubah sejak consent terakhir. Berikan consent baru sebelum
                data kandidat dikirim lagi.
              </Alert>
            ) : null}

            {status?.required_text ? (
              <Stack gap="xs">
                <Textarea
                  label={`Teks consent (versi ${status.required_text.text_version})`}
                  value={status.required_text.display_text}
                  readOnly
                  autosize
                  minRows={4}
                  maxRows={12}
                />
                <Text size="xs" c="dimmed">
                  sha256: <Code>{status.required_text.text_sha256}</Code>
                </Text>
              </Stack>
            ) : null}

            {status?.granted && status.current ? (
              <Stack gap="xs" mt="sm">
                <Text size="sm">
                  Diberikan {status.current.granted_at} · teks {status.current.text_version} ·
                  provider {status.current.scope.provider_id}
                </Text>
                <Button
                  variant="light"
                  color="red"
                  loading={revoke.isPending}
                  onClick={() => void revoke.mutate(status.current?.consent_id ?? "")}
                >
                  Cabut consent
                </Button>
              </Stack>
            ) : scope ? (
              <Stack gap="xs" mt="sm">
                <Checkbox
                  checked={accepted}
                  onChange={(event) => setAccepted(event.currentTarget.checked)}
                  label="Saya sudah membaca teks consent di atas dan menyetujuinya."
                />
                <Button
                  disabled={!accepted || grant.isPending}
                  onClick={() =>
                    void grant.mutate({
                      providerId: scope.provider_id,
                      dataClasses: scope.data_classes,
                    })
                  }
                >
                  Berikan consent
                </Button>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Provider aktif tidak mengirim data ke layanan eksternal.
              </Text>
            )}

            {status?.history.length ? (
              <Stack gap="xs" mt="md">
                <Text fw={500} size="sm">
                  Riwayat consent
                </Text>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Diberikan</Table.Th>
                      <Table.Th>Provider</Table.Th>
                      <Table.Th>Teks</Table.Th>
                      <Table.Th>Dicabut</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {status.history.map((record) => (
                      <Table.Tr key={record.consent_id}>
                        <Table.Td>{record.granted_at}</Table.Td>
                        <Table.Td>{record.scope.provider_id}</Table.Td>
                        <Table.Td>{record.text_version}</Table.Td>
                        <Table.Td>{record.revoked_at ?? "—"}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                {status.history_truncated ? (
                  <Text size="xs" c="dimmed">
                    Riwayat lebih lama tidak ditampilkan.
                  </Text>
                ) : null}
              </Stack>
            ) : null}
          </Card>

          <Card withBorder>
            <Text fw={500}>Retensi</Text>
            <Text size="sm" c="dimmed">
              Durasi retensi masih sementara sampai D10 disetujui.
            </Text>
          </Card>

          <SourceRegistry editable />
        </Stack>
      ) : null}
    </PageFrame>
  );
}
