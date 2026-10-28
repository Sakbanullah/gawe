import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import type { ApplicationList, ApplicationSummary } from "../app/apiClient";
import { friendlyError } from "../app/errors";
import { APPLICATION_STATUS, ELIGIBILITY, label } from "../app/labels";
import {
  useApplications,
  useCancelApplication,
  useCreateApplicationFromUrl,
  useOverview,
} from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { EmptyState, type PageState } from "../components/states";

// Codes the URL form can answer with; each one has a different next step, so
// each one gets its own title (API-CONTRACTS.md §3.4).
const URL_ERROR_TITLE: Record<string, string> = {
  source_not_found: "Alamat lowongan tidak ditemukan",
  manual_fetch_failed: "Halaman tidak bisa dibaca otomatis",
  robots_disallowed: "Situs ini tidak mengizinkan pembacaan otomatis",
  manual_page_unreadable: "Isi halaman tidak terbaca",
};

export function ApplicationsPage() {
  const overview = useOverview();
  const applications = useApplications();
  const createFromUrl = useCreateApplicationFromUrl();
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [pasteOpen, setPasteOpen] = useState(false);
  const [showCancelled, setShowCancelled] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const cancelMutation = useCancelApplication();
  const [pendingCancel, setPendingCancel] = useState<ApplicationSummary | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const state: PageState = applications.isPending
    ? "loading"
    : applications.isError
      ? "error"
      : "ready";

  const allItems: ApplicationList["items"] = applications.data?.items ?? [];
  const items = showCancelled ? allItems : allItems.filter((item) => item.status !== "cancelled");
  const cancelledCount = allItems.length - items.length;
  const locked = overview.data ? overview.data.profile?.status !== "confirmed" : false;
  const errorCode = createFromUrl.error && "code" in createFromUrl.error ? String(createFromUrl.error.code) : "";

  return (
    <PageFrame
      eyebrow="Langkah 4"
      title="Lamaran saya"
      description="Setiap lowongan yang kamu lamar punya ruang sendiri: CV, surat lamaran, dan statusnya."
      state={state}
      onRetry={() => void applications.refetch()}
      action={
        <Button onClick={() => setShowAddForm((v) => !v)} variant={showAddForm ? "light" : "filled"}>
          {showAddForm ? "Tutup formulir" : "Tambah lowongan"}
        </Button>
      }
    >
      <Stack gap="lg">
        {locked ? (
          <Alert color="orange" title="Selesaikan CV-mu dulu">
            <Stack gap="sm" align="flex-start">
              <Text size="sm">
                Konfirmasi data CV-mu sebelum mulai menyiapkan lamaran.
              </Text>
              <Button component={Link} to="/master-cv" variant="light">
                Buka CV Utama
              </Button>
            </Stack>
          </Alert>
        ) : null}

        {showAddForm && !locked ? (
          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Tambah lowongan dari alamat halaman</Title>
              <Text size="sm" c="dimmed">
                Tempel alamat halaman lowongan. Gawe membacanya sekali untuk membuat ruang lamaran
                ini.
              </Text>
              <TextInput
                label="Alamat lowongan"
                description="Diawali https:// dan bisa dibuka tanpa login."
                placeholder="https://contoh.com/karier/backend-engineer"
                value={url}
                onChange={(event) => setUrl(event.currentTarget.value)}
              />
              <Accordion
                variant="contained"
                value={pasteOpen ? "paste" : null}
                onChange={(value) => setPasteOpen(value === "paste")}
              >
                <Accordion.Item value="paste">
                  <Accordion.Control>Halaman tidak bisa dibaca? Tempel teksnya</Accordion.Control>
                  <Accordion.Panel>
                    <Textarea
                      label="Teks lowongan"
                      description="Salin isi halaman lowongan ke sini. Baris pertama jadi judul."
                      placeholder={"Senior Backend Engineer - Acme\n\nKami mencari backend engineer..."}
                      value={text}
                      onChange={(event) => setText(event.currentTarget.value)}
                      minRows={6}
                      maxLength={200000}
                    />
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
              <Button
                loading={createFromUrl.isPending}
                disabled={url.trim() === ""}
                onClick={() =>
                  void createFromUrl
                    .mutateAsync({ url: url.trim(), text: text.trim() || undefined })
                    .then(() => {
                      setUrl("");
                      setText("");
                      setPasteOpen(false);
                      setShowAddForm(false);
                    })
                    .catch(() => undefined)
                }
              >
                Tambah lowongan ini
              </Button>
            </Stack>
          </Card>
        ) : null}

        {createFromUrl.isError ? (
          <Alert color="red" title={URL_ERROR_TITLE[errorCode] ?? "Alamat belum bisa dipakai"}>
            <Stack gap="sm" align="flex-start">
              <Text size="sm">{friendlyError(createFromUrl.error)}</Text>
              {errorCode in URL_ERROR_TITLE ? (
                <Button size="compact-sm" variant="light" onClick={() => setPasteOpen(true)}>
                  Tempel teks lowongan
                </Button>
              ) : null}
            </Stack>
          </Alert>
        ) : null}

        {items.length === 0 ? (
          <EmptyState
            title="Belum ada lamaran"
            message="Mulai dari daftar lowongan. Pilih satu yang cocok, lalu siapkan CV dan surat lamarannya."
            action={
              <Button component={Link} to="/matches">
                Lihat lowongan
              </Button>
            }
          />
        ) : (
          <Card withBorder>
            <Stack gap="md">
              <Title order={3}>Daftar lamaran</Title>
              <Table.ScrollContainer minWidth={640}>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Lowongan</Table.Th>
                      <Table.Th>Syarat</Table.Th>
                      <Table.Th>Kecocokan</Table.Th>
                      <Table.Th>Status</Table.Th>
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
                          <Text size="sm" fw={500}>
                            {item.job.title}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {item.job.company} · {item.job.location?.raw ?? "lokasi tidak dicantumkan"}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge
                            variant="light"
                            color={item.eligibility_status === "eligible" ? "teal" : "orange"}
                          >
                            {item.eligibility_status
                              ? label(ELIGIBILITY, item.eligibility_status)
                              : "Belum diperiksa"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {item.fit_score === null || item.fit_score === undefined
                              ? "Belum dihitung"
                              : `${item.fit_score} dari 100`}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{label(APPLICATION_STATUS, item.status)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs" wrap="nowrap">
                            <Button
                              component={Link}
                              to={`/applications/${item.application_id}`}
                              size="compact-sm"
                              variant="light"
                            >
                              Buka
                            </Button>
                            {item.status === "cancelled" ? null : (
                              <Button
                                size="compact-sm"
                                variant="subtle"
                                color="red"
                                disabled={item.status === "approved" || item.status === "processing"}
                                onClick={() => {
                                  setCancelReason("");
                                  setPendingCancel(item);
                                }}
                              >
                                Hentikan
                              </Button>
                            )}
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>

              {allItems.length > 0 ? (
                <Group justify="flex-start">
                  <Button
                    size="compact-sm"
                    variant="subtle"
                    onClick={() => setShowCancelled((value) => !value)}
                  >
                    {showCancelled
                      ? "Sembunyikan yang dihentikan"
                      : `Tampilkan yang dihentikan (${cancelledCount})`}
                  </Button>
                </Group>
              ) : null}
            </Stack>
          </Card>
        )}
      </Stack>

      <Modal
        opened={pendingCancel !== null}
        onClose={() => setPendingCancel(null)}
        title="Hentikan lamaran ini?"
      >
        <Stack>
          <Text size="sm">
            Lamaran untuk <strong>{pendingCancel?.job.title}</strong> akan dipindahkan ke daftar
            yang dihentikan. Dokumen dan riwayatnya tidak dihapus, dan bisa kamu lihat lagi nanti.
          </Text>
          <Textarea
            label="Alasan (boleh dikosongkan)"
            placeholder="Contoh: lowongan sudah ditutup"
            value={cancelReason}
            onChange={(event) => setCancelReason(event.currentTarget.value)}
            maxLength={500}
          />
          {cancelMutation.isError ? (
            <Alert color="red" title="Belum berhasil">
              {friendlyError(cancelMutation.error)}
            </Alert>
          ) : null}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPendingCancel(null)}>
              Batal
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
              Hentikan lamaran
            </Button>
          </Group>
        </Stack>
      </Modal>
    </PageFrame>
  );
}


