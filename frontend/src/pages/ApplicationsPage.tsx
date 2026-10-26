import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import { ApiError, type ApplicationList, type ApplicationSummary } from "../app/apiClient";
import {
  useApplications,
  useCancelApplication,
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
  cancelled: "Dibatalkan",
};

export function ApplicationsPage() {
  const overview = useOverview();
  const applications = useApplications();
  const createFromUrl = useCreateApplicationFromUrl();
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [showCancelled, setShowCancelled] = useState(false);
  const cancelMutation = useCancelApplication();
  const [pendingCancel, setPendingCancel] = useState<ApplicationSummary | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const state: PageState = applications.isPending
    ? "loading"
    : applications.isError
      ? "error"
      : "ready";

  const allItems: ApplicationList["items"] = applications.data?.items ?? [];
  const items = showCancelled
    ? allItems
    : allItems.filter((item) => item.status !== "cancelled");
  const cancelledCount = allItems.length - items.length;
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
      {allItems.length > 0 ? (
        <Group justify="flex-end">
          <Button
            size="compact-sm"
            variant="subtle"
            onClick={() => setShowCancelled((value) => !value)}
          >
            {showCancelled
              ? "Sembunyikan yang dibatalkan"
              : `Tampilkan yang dibatalkan (${cancelledCount})`}
          </Button>
        </Group>
      ) : null}
      {items.length > 0 ? (
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Lowongan</Table.Th>
              <Table.Th>Eligibility</Table.Th>
              <Table.Th>Fit</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Dokumen</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((item) => (
              <Table.Tr
                key={item.application_id}
                opacity={item.status === "cancelled" ? 0.55 : undefined}
              >
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
                  <Badge variant="outline" color={item.status === "cancelled" ? "gray" : undefined}>
                    {STATUS_LABEL[item.status] ?? item.status}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">
                    CV {item.document_counts?.cv_versions ?? 0} · CL{" "}
                    {item.document_counts?.cover_letter_versions ?? 0}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {item.status === "cancelled" ? null : (
                    <Button
                      size="compact-xs"
                      variant="subtle"
                      color="red"
                      disabled={item.status === "approved" || item.status === "processing"}
                      onClick={() => {
                        setCancelReason("");
                        setPendingCancel(item);
                      }}
                    >
                      Batalkan
                    </Button>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}
      <Modal
        opened={pendingCancel !== null}
        onClose={() => setPendingCancel(null)}
        title="Batalkan application?"
        centered
      >
        <Stack>
          <Text size="sm">
            Workspace <strong>{pendingCancel?.job.title}</strong> akan diarsipkan dan hilang
            dari daftar aktif. Dokumen dan riwayat approval tetap tersimpan, tidak dihapus.
          </Text>
          <Textarea
            label="Alasan (opsional)"
            placeholder="Contoh: lowongan sudah ditutup"
            value={cancelReason}
            onChange={(event) => setCancelReason(event.currentTarget.value)}
            maxLength={500}
          />
          {cancelMutation.isError ? (
            <Alert color="red" title="Gagal membatalkan">
              {cancelMutation.error instanceof ApiError
                ? cancelMutation.error.message
                : "Coba lagi."}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPendingCancel(null)}>
              Kembali
            </Button>
            <Button
              color="red"
              loading={cancelMutation.isPending}
              onClick={() => {
                if (!pendingCancel) return;
                cancelMutation.mutate(
                  { applicationId: pendingCancel.application_id, reason: cancelReason || null },
                  { onSuccess: () => setPendingCancel(null) },
                );
              }}
            >
              Batalkan
            </Button>
          </Group>
        </Stack>
      </Modal>
    </PageFrame>
  );
}
