import { Alert, Badge, Button, Card, Group, Stack, Table, Text } from "@mantine/core";
import { Link } from "react-router";

import type { DiscoveryRun } from "../app/apiClient";
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
import type { PageState } from "../components/states";

const STATUS_COLOR: Record<string, string> = {
  completed: "green",
  partial: "yellow",
  failed: "red",
  processing: "blue",
  queued: "gray",
  skipped: "gray",
};

function StatusBadge({ status }: { status: string }) {
  return <Badge color={STATUS_COLOR[status] ?? "gray"}>{status}</Badge>;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Permintaan gagal.";
}

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
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="sm">
            <Text fw={500}>Run terakhir</Text>
            <StatusBadge status={run.status} />
          </Group>
          <Text size="sm" c="dimmed">
            {run.started_at}
          </Text>
        </Group>

        {run.status === "partial" ? (
          <Alert color="yellow" title="Hasil sebagian">
            Sebagian sumber gagal. Hasil sumber yang berhasil tetap disimpan.
          </Alert>
        ) : null}

        <Text size="sm">
          Diambil {run.counts.fetched ?? 0} · baru {run.counts.new_jobs ?? 0} · duplikat{" "}
          {run.counts.duplicates ?? 0}
        </Text>

        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Sumber</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Diambil</Table.Th>
              <Table.Th>Baru</Table.Th>
              <Table.Th>Duplikat</Table.Th>
              <Table.Th>Terakhir</Table.Th>
              <Table.Th>Error</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {run.sources.map((source) => (
              <Table.Tr key={source.source_id}>
                <Table.Td>{source.company}</Table.Td>
                <Table.Td>
                  <StatusBadge status={source.status} />
                </Table.Td>
                <Table.Td>{source.fetched_count}</Table.Td>
                <Table.Td>{source.accepted_count}</Table.Td>
                <Table.Td>{source.duplicate_count}</Table.Td>
                <Table.Td>{source.last_attempt_at ?? "—"}</Table.Td>
                <Table.Td>{source.error ? source.error.message : "—"}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>

        {retryError ? <Alert color="red">{errorText(retryError)}</Alert> : null}
        {retryable ? (
          <Group>
            <Button variant="light" loading={retrying} onClick={onRetry}>
              Ulangi sumber gagal
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
      title="Discovery"
      description="Sumber lowongan, progress, dan error per sumber."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void sources.refetch();
        void runs.refetch();
      }}
    >
      {!confirmed ? (
        <Alert color="orange" title="Discovery terkunci">
          <Stack gap="xs">
            <Text>Discovery hanya tersedia setelah profil dikonfirmasi.</Text>
            <Group>
              <Button component={Link} to="/master-cv" variant="light">
                Buka Master CV
              </Button>
            </Group>
          </Stack>
        </Alert>
      ) : (
        <Stack gap="md">
          <Card withBorder>
            <Group justify="space-between">
              <Text size="sm">
                {fetchable.length} sumber verified dan aktif siap dijalankan.
              </Text>
              <Button
                disabled={fetchable.length === 0 || start.isPending}
                loading={start.isPending}
                onClick={() => start.mutate()}
              >
                Jalankan discovery
              </Button>
            </Group>
            {start.error ? <Alert color="red" mt="sm">{errorText(start.error)}</Alert> : null}
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
            <Alert color="gray" title="Belum ada run discovery">
              Jalankan discovery untuk mengambil lowongan dari sumber terverifikasi.
            </Alert>
          )}

          <SourceRegistry />
        </Stack>
      )}
    </PageFrame>
  );
}
