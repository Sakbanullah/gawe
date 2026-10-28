import { Alert, Button, Card, Group, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import type { DiscoveryRun } from "../app/apiClient";
import { friendlyError } from "../app/errors";
import { RUN_STATUS, label } from "../app/labels";
import {
  useDiscoveryRuns,
  useOverview,
  useRetryTask,
  useSources,
  useStartDiscoveryRun,
  useTask,
} from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { SourceRegistry } from "../components/SourceRegistry";
import { EmptyState, PartialState, StatusBadge, type PageState } from "../components/states";

function RunCard({
  run,
  retryable,
  retrying,
  retryError,
  onRetry,
}: {
  run: DiscoveryRun;
  retryable: boolean;
  retrying: boolean;
  retryError: unknown;
  onRetry: () => void;
}) {
  const incomplete = run.sources.filter(
    (source) =>
      (source.stats?.truncated ?? 0) > 0 ||
      (source.stats?.stale ?? 0) > 0 ||
      (source.stats?.skipped ?? 0) > 0 ||
      (source.stats?.invalid ?? 0) > 0,
  );
  const failed = run.sources.filter((source) => source.status === "failed");

  return (
    <Card withBorder>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <Title order={3}>Pencarian terakhir</Title>
            <StatusBadge status={run.status} label={label(RUN_STATUS, run.status)} />
          </Group>
          <Text size="sm" c="dimmed">
            {run.started_at}
          </Text>
        </Group>

        <Text>
          Gawe menemukan <strong>{run.counts.new_jobs ?? 0} lowongan baru</strong> dari{" "}
          {run.sources.length} perusahaan. {run.counts.duplicates ?? 0} lowongan sudah pernah ada.
        </Text>

        {run.status === "partial" ? (
          <PartialState message="Sebagian perusahaan tidak bisa dihubungi. Lowongan yang berhasil diambil tetap disimpan." />
        ) : null}

        {run.error ? (
          <Alert color="orange" title="Pemeriksaan syarat belum selesai">
            <Text size="sm">
              Lowongan sudah tersimpan, tetapi pemeriksaan syarat dan kecocokan gagal. Coba jalankan
              ulang pencarian.
            </Text>
          </Alert>
        ) : null}

        {incomplete.length > 0 ? (
          <Alert color="orange" title="Sebagian data tidak lengkap">
            <Stack gap={4}>
              {incomplete.map((source) => (
                <Text key={source.source_id} size="sm">
                  {source.company}:{" "}
                  {[
                    source.stats?.truncated
                      ? `${source.stats.truncated} deskripsi dipotong`
                      : null,
                    source.stats?.stale ? `${source.stats.stale} data lama` : null,
                    source.stats?.skipped ? `${source.stats.skipped} dilewati` : null,
                    source.stats?.invalid ? `${source.stats.invalid} tidak valid` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
              ))}
            </Stack>
          </Alert>
        ) : null}

        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Perusahaan</Table.Th>
              <Table.Th>Hasil</Table.Th>
              <Table.Th>Lowongan baru</Table.Th>
              <Table.Th>Keterangan</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {run.sources.map((source) => (
              <Table.Tr key={source.source_id}>
                <Table.Td>{source.company}</Table.Td>
                <Table.Td>
                  <StatusBadge status={source.status} label={label(RUN_STATUS, source.status)} />
                </Table.Td>
                <Table.Td>{source.accepted_count}</Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {source.error
                      ? "Tidak bisa dihubungi"
                      : source.duplicate_count > 0
                        ? `${source.duplicate_count} lowongan sudah pernah ada`
                        : "—"}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>

        {retryError ? (
          <Alert color="red" title="Belum berhasil">
            {friendlyError(retryError)}
          </Alert>
        ) : null}
        {retryable && failed.length > 0 ? (
          <Group>
            <Button variant="light" loading={retrying} onClick={onRetry}>
              Coba lagi perusahaan yang gagal
            </Button>
          </Group>
        ) : null}
      </Stack>
    </Card>
  );
}

export function DiscoveryPage() {
  const overview = useOverview();
  const sources = useSources();
  const runs = useDiscoveryRuns();
  const start = useStartDiscoveryRun();
  const retry = useRetryTask();
  const [notice, setNotice] = useState<string | null>(null);
  const latest = runs.data?.items[0] ?? null;
  const task = useTask(latest?.task_id ?? null);

  const loading = overview.isPending || sources.isPending || runs.isPending;
  const failed = overview.isError || sources.isError || runs.isError;
  const state: PageState = loading ? "loading" : failed ? "error" : "ready";
  const profile = overview.data?.profile;
  const confirmed = profile?.status === "confirmed" && profile.active === true;
  const fetchable = (sources.data?.items ?? []).filter(
    (source) => source.enabled && source.verification_status === "verified",
  );

  return (
    <PageFrame
      eyebrow="Langkah 2"
      title="Cari Lowongan"
      description="Gawe mengambil lowongan terbaru dari perusahaan yang sudah terdaftar, lalu memeriksa mana yang sesuai dengan syaratmu."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void sources.refetch();
        void runs.refetch();
      }}
    >
      {!confirmed ? (
        <Alert color="orange" title="Selesaikan CV-mu dulu">
          <Stack gap="sm" align="flex-start">
            <Text size="sm">
              Gawe baru bisa mencari lowongan setelah data CV-mu dikonfirmasi. Ini supaya lowongan
              yang muncul benar-benar sesuai.
            </Text>
            <Button component={Link} to="/master-cv" variant="light">
              Buka CV Utama
            </Button>
          </Stack>
        </Alert>
      ) : (
        <Stack gap="lg">
          <Card withBorder>
            <Stack gap="sm">
              <Group justify="space-between" wrap="wrap" gap="sm">
                <div>
                  <Text fw={600}>Mulai pencarian baru</Text>
                  <Text size="sm" c="dimmed">
                    {fetchable.length > 0
                      ? `${fetchable.length} perusahaan siap dicek. Biasanya selesai dalam beberapa menit.`
                      : "Belum ada perusahaan yang siap dicek. Tambahkan dulu di bagian Sumber lowongan."}
                  </Text>
                </div>
                <Button
                  size="md"
                  disabled={fetchable.length === 0 || start.isPending}
                  loading={start.isPending}
                  onClick={() =>
                    start.mutate(undefined, {
                      onSuccess: () =>
                        setNotice("Pencarian dimulai. Hasilnya muncul di bawah setelah selesai."),
                    })
                  }
                >
                  Cari lowongan sekarang
                </Button>
              </Group>
              {start.error ? (
                <Alert color="red" title="Pencarian belum bisa dimulai">
                  {friendlyError(start.error)}
                </Alert>
              ) : null}
              {notice ? (
                <Alert color="indigo" title="Pencarian dimulai">
                  {notice}
                </Alert>
              ) : null}
            </Stack>
          </Card>

          {latest ? (
            <RunCard
              run={latest}
              retryable={task.data?.retry.retryable === true}
              retrying={retry.isPending}
              retryError={retry.error}
              onRetry={() => retry.mutate({ taskId: latest.task_id })}
            />
          ) : (
            <EmptyState
              title="Belum pernah mencari"
              message="Tekan Cari lowongan sekarang untuk mengambil lowongan pertama kalinya."
            />
          )}

          <SourceRegistry />
        </Stack>
      )}
    </PageFrame>
  );
}
