import { Alert, Group, Stack, Text, Title } from "@mantine/core";
import { useParams } from "react-router";

import { useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { StatusBadge, type PageState } from "../components/states";

export function ApplicationWorkspacePage() {
  const { id } = useParams();
  const overview = useOverview();
  const state: PageState = overview.isPending ? "loading" : overview.isError ? "error" : "empty";

  return (
    <PageFrame
      title="Application Workspace"
      description={`Application ${id ?? "-"}.`}
      state={state}
      onRetry={() => void overview.refetch()}
    >
      <Stack gap="md">
        <Group>
          <Text fw={500}>Status dokumen</Text>
          <StatusBadge status="draft" />
        </Group>
        <Title order={4}>CV</Title>
        <Text c="dimmed">Belum ada versi CV.</Text>
        <Title order={4}>Cover letter</Title>
        <Text c="dimmed">Belum ada versi cover letter.</Text>
        <Alert color="gray" title="Approval per versi">
          Approval terikat pada versi dan hash. Ekspor hanya dari versi approved.
        </Alert>
      </Stack>
    </PageFrame>
  );
}
