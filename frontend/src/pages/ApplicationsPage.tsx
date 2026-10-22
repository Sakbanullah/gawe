import {
  Alert,
  Badge,
  Button,
  Group,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import { ApiError, type ApplicationList } from "../app/apiClient";
import {
  useApplications,
  useCreateApplicationFromUrl,
  useOverview,
} from "../app/queries";
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
  const createFromUrl = useCreateApplicationFromUrl();
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
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
      <Group align="flex-end">
        <TextInput
          label="Tambah dari URL lowongan"
          description="HTTPS publik. Halaman dibaca sekali untuk workspace ini."
          placeholder="https://contoh.com/karier/backend-engineer"
          value={url}
          onChange={(event) => setUrl(event.currentTarget.value)}
          style={{ flex: 1 }}
          disabled={locked}
        />
        <Button
          loading={createFromUrl.isPending}
          disabled={locked || url.trim() === ""}
          onClick={() =>
            void createFromUrl
              .mutateAsync({ url: url.trim(), text: text.trim() || undefined })
              .then(() => {
                setUrl("");
                setText("");
                setShowText(false);
              })
          }
        >
          Buat workspace
        </Button>
      </Group>
      <Group justify="space-between">
        <Button
          variant="subtle"
          size="compact-sm"
          onClick={() => setShowText((current) => !current)}
          disabled={locked}
        >
          {showText ? "Sembunyikan teks lowongan" : "Halaman tidak bisa dibaca? Tempel teksnya"}
        </Button>
      </Group>
      {showText ? (
        <Textarea
          label="Teks lowongan"
          description="Untuk halaman yang menolak akses otomatis (403/429) atau dirender JavaScript. Baris pertama menjadi judul. URL di atas tetap wajib."
          placeholder={"Senior Backend Engineer - Acme\n\nKami mencari backend engineer..."}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
          minRows={6}
          maxLength={200000}
          disabled={locked}
        />
      ) : null}
      {createFromUrl.isError ? (
        <Alert color="red" title="URL ditolak">
          {createFromUrl.error instanceof ApiError
            ? createFromUrl.error.message
            : "URL tidak dapat dipakai."}
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
