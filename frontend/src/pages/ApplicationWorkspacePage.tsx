import { Alert, Badge, Button, Divider, Group, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { ApplicationWorkspace } from "../app/apiClient";
import { useApplication, useGenerateDocuments, useRerunAnalysis } from "../app/queries";
import { DocumentReviewPanel } from "../components/DocumentReviewPanel";
import { PageFrame } from "../components/PageFrame";
import { StatusBadge, type PageState } from "../components/states";

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

export function ApplicationWorkspacePage() {
  const { id } = useParams();
  const application = useApplication(id);
  const rerun = useRerunAnalysis();
  const generate = useGenerateDocuments();
  const [selected, setSelected] = useState<string | null>(null);
  const state: PageState = application.isPending
    ? "loading"
    : application.isError
      ? "error"
      : "ready";

  const data: ApplicationWorkspace | undefined = application.data;
  const eligible = data?.eligibility?.status === "eligible";

  return (
    <PageFrame
      title="Application Workspace"
      description={data ? `${data.job.title} · ${data.job.company}` : undefined}
      state={state}
      onRetry={() => void application.refetch()}
    >
      {data ? (
        <Stack gap="md">
          <Group>
            <Text fw={500}>Status</Text>
            <Badge variant="outline">{STATUS_LABEL[data.status] ?? data.status}</Badge>
            <Button
              variant="light"
              loading={rerun.isPending}
              onClick={() => void rerun.mutateAsync(data.application_id)}
            >
              Analisis ulang
            </Button>
          </Group>

          {data.eligibility ? (
            <>
              <Divider label="Eligibility" labelPosition="left" />
              <Group>
                <StatusBadge status={data.eligibility.status} />
                {data.eligibility.reason_summary ? (
                  <Text size="sm">{data.eligibility.reason_summary}</Text>
                ) : null}
              </Group>
              {data.eligibility.status !== "eligible" ? (
                <Alert color="orange" title="Dokumen diblokir">
                  Eligibility {data.eligibility.status}. Dokumen hanya dibuat untuk eligibility
                  eligible.
                </Alert>
              ) : null}
            </>
          ) : null}

          {data.fit ? (
            <>
              <Divider label="Fit" labelPosition="left" />
              <Group>
                <Text fw={500}>Fit {data.fit.fit_score}</Text>
                <Badge variant="light">{data.fit.verdict}</Badge>
                <Badge variant="light">{data.fit.confidence}</Badge>
              </Group>
            </>
          ) : (
            <Alert color="gray">Fit belum dihitung. Eligibility harus eligible lebih dulu.</Alert>
          )}

          <Divider label="Dokumen" labelPosition="left" />
          {eligible ? (
            <Group>
              <Button
                variant="light"
                loading={generate.isPending}
                onClick={() =>
                  void generate.mutateAsync({
                    applicationId: data.application_id,
                    kinds: ["cv"],
                    language: "en",
                  })
                }
              >
                Buat CV
              </Button>
              <Button
                variant="light"
                loading={generate.isPending}
                onClick={() =>
                  void generate.mutateAsync({
                    applicationId: data.application_id,
                    kinds: ["cover_letter"],
                    language: "en",
                  })
                }
              >
                Buat cover letter
              </Button>
              <Text size="xs" c="dimmed">
                Draft deterministik dari profil confirmed. PDF dan ekspor belum tersedia.
              </Text>
            </Group>
          ) : (
            <Alert color="gray">
              Pembuatan dokumen hanya tersedia saat eligibility eligible.
            </Alert>
          )}
          {generate.isError ? (
            <Alert color="red">Pembuatan dokumen gagal. Coba lagi.</Alert>
          ) : null}
          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Jenis</Table.Th>
                <Table.Th>Versi</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Review</Table.Th>
                <Table.Th>Aksi</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.documents.cv.length === 0 && data.documents.cover_letter.length === 0 ? (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text c="dimmed">
                      Belum ada versi dokumen. Buat draft saat eligibility eligible.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ) : (
                [...data.documents.cv, ...data.documents.cover_letter].map((document) => (
                  <Table.Tr key={document.document_version_id}>
                    <Table.Td>
                      {document.kind === "cv" ? "CV" : "Cover letter"}
                    </Table.Td>
                    <Table.Td>{document.version}</Table.Td>
                    <Table.Td>
                      <StatusBadge status={document.status} />
                      {document.approved ? (
                        <Badge ml="xs" color="green" variant="light">
                          approved
                        </Badge>
                      ) : null}
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light">{document.review_status}</Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        variant="subtle"
                        size="xs"
                        onClick={() => setSelected(document.document_version_id)}
                      >
                        Lihat
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))
              )}
            </Table.Tbody>
          </Table>

          {selected ? (
            <DocumentReviewPanel
              applicationId={data.application_id}
              documentVersionId={selected}
              onClose={() => setSelected(null)}
            />
          ) : null}

          <Divider label="Nama file" labelPosition="left" />
          <Stack gap={4}>
            <Text size="sm">CV: {data.suggested_filenames.cv}</Text>
            <Text size="sm">Cover letter: {data.suggested_filenames.cover_letter}</Text>
            <Text size="xs" c="dimmed">
              Nama dihitung backend. Mengubah nama tidak mengubah isi atau approval.
            </Text>
          </Stack>

          <Divider label="Apply" labelPosition="left" />
          {data.job.apply_url ? (
            <Group>
              <Button
                component="a"
                href={data.job.apply_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Buka halaman lamaran resmi
              </Button>
              <Text size="xs" c="dimmed">
                Gawe tidak mengirim lamaran. Submit dilakukan di situs resmi.
              </Text>
            </Group>
          ) : (
            <Alert color="gray">Sumber tidak menyediakan URL lamaran.</Alert>
          )}

          <Divider label="Langkah berikutnya" labelPosition="left" />
          <Stack gap={4}>
            <Title order={5}>{data.next_action.label ?? data.next_action.code}</Title>
            {data.next_action.reason ? (
              <Text size="sm" c="dimmed">
                {data.next_action.reason}
              </Text>
            ) : null}
            <Text size="sm" component={Link} to="/matches">
              Kembali ke Job Matches
            </Text>
          </Stack>
        </Stack>
      ) : null}
    </PageFrame>
  );
}
