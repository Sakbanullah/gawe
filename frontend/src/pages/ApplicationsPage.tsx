import { Alert, Badge, Table, Text } from "@mantine/core";
import { Link } from "react-router";

import type { ApplicationList } from "../app/apiClient";
import { useApplications, useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { EmptyState, type PageState } from "../components/states";

const STATUS_LABEL: Record<string, string> = {
  not_started: "Not started",
  processing: "Processing",
  needs_review: "Needs review",
  in_review: "In review",
  approved: "Approved",
  exported: "Exported",
  failed: "Failed",
  outdated: "Outdated",
};

export function ApplicationsPage() {
  const overview = useOverview();
  const applications = useApplications();
  const state: PageState = applications.isPending
    ? "loading"
    : applications.isError
      ? "error"
      : "ready";

  const items: ApplicationList["items"] = applications.data?.items ?? [];
  const locked = overview.data ? overview.data.profile?.status !== "confirmed" : false;

  return (
    <PageFrame
      title="Applications"
      description="Satu workspace per lowongan. CV dan cover letter dipisahkan."
      state={state}
      onRetry={() => void applications.refetch()}
    >
      {locked ? (
        <Alert color="orange" title="Profil belum dikonfirmasi">
          Konfirmasi profil sebelum membuat workspace lamaran.
        </Alert>
      ) : null}
      {items.length === 0 ? <EmptyState message="Belum ada application." /> : null}
      {items.length > 0 ? (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Lowongan</Table.Th>
              <Table.Th>Eligibility</Table.Th>
              <Table.Th>Fit</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Dokumen</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((item) => (
              <Table.Tr key={item.application_id}>
                <Table.Td>
                  <Text component={Link} to={`/applications/${item.application_id}`} fw={500}>
                    {item.job.title}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {item.job.company}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light">{item.eligibility_status ?? "unknown"}</Badge>
                </Table.Td>
                <Table.Td>
                  {item.fit_score === null || item.fit_score === undefined
                    ? "—"
                    : `Fit ${item.fit_score}`}
                </Table.Td>
                <Table.Td>
                  <Badge variant="outline">{STATUS_LABEL[item.status] ?? item.status}</Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">
                    CV {item.document_counts?.cv_versions ?? 0} · CL{" "}
                    {item.document_counts?.cover_letter_versions ?? 0}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}
    </PageFrame>
  );
}
