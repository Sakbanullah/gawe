import {
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Group,
  Progress,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import type { ApplicationWorkspace } from "../app/apiClient";
import { friendlyError } from "../app/errors";
import {
  APPLICATION_STATUS,
  DOCUMENT_STATUS,
  ELIGIBILITY,
  FIT_VERDICT,
  NEXT_ACTION,
  REVIEW_STATUS,
  label,
} from "../app/labels";

/** The backend says which step comes next; the wording for it lives here. */
function hintFor(code: string): string {
  return (NEXT_ACTION[code] ?? NEXT_ACTION.none).hint;
}
import { useApplication, useGenerateDocuments, useRerunAnalysis } from "../app/queries";
import { DocumentReviewPanel } from "../components/DocumentReviewPanel";
import { PageFrame } from "../components/PageFrame";
import type { PageState } from "../components/states";

export function ApplicationWorkspacePage() {
  const { id } = useParams();
  const application = useApplication(id);
  const rerun = useRerunAnalysis();
  const generate = useGenerateDocuments();
  const [selected, setSelected] = useState<string | null>(null);
  // Which button started the running generation; the other one stays disabled.
  const [pendingKind, setPendingKind] = useState<"cv" | "cover_letter" | null>(null);
  const busyKind = generate.isPending ? pendingKind : null;
  useEffect(() => {
    if (!generate.isPending) setPendingKind(null);
  }, [generate.isPending]);
  const state: PageState = application.isPending
    ? "loading"
    : application.isError
      ? "error"
      : "ready";

  const data: ApplicationWorkspace | undefined = application.data;
  const eligible = data?.eligibility?.status === "eligible";
  const documents = data ? [...data.documents.cv, ...data.documents.cover_letter] : [];
  const approvedCv = data?.documents.cv.find((document) => document.approved);
  const approvedCoverLetter = data?.documents.cover_letter.find((document) => document.approved);

  return (
    <PageFrame
      eyebrow="Lamaran"
      title={data ? data.job.title : "Lamaran"}
      description={
        data
          ? `${data.job.company} · ${data.job.location?.raw ?? "lokasi tidak dicantumkan"}`
          : undefined
      }
      state={state}
      onRetry={() => void application.refetch()}
      action={
        <Button component={Link} to="/applications" variant="light">
          Semua lamaran
        </Button>
      }
    >
      {data ? (
        <Stack gap="lg">
          <Card withBorder>
            <Group justify="space-between" wrap="wrap" gap="md">
              <div>
                <Text size="xs" fw={600} tt="uppercase" c="dimmed">
                  Status lamaran
                </Text>
                <Text fw={600} size="lg" mt={2}>
                  {label(APPLICATION_STATUS, data.status)}
                </Text>
              </div>
              <Button
                variant="subtle"
                loading={rerun.isPending}
                onClick={() => void rerun.mutateAsync(data.application_id)}
              >
                Periksa ulang lowongan ini
              </Button>
            </Group>
            {data.next_action.reason ? (
              <Text size="sm" c="dimmed" mt="sm">
                {hintFor(data.next_action.code)}
              </Text>
            ) : null}
            {rerun.isError ? (
              <Alert color="red" mt="sm" title="Belum berhasil">
                {friendlyError(rerun.error)}
              </Alert>
            ) : null}
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Apakah kamu memenuhi syaratnya?</Title>
              {data.eligibility ? (
                <>
                  <Group gap="xs">
                    <Badge
                      variant="light"
                      color={
                        data.eligibility.status === "eligible"
                          ? "teal"
                          : data.eligibility.status === "ineligible"
                            ? "red"
                            : "orange"
                      }
                    >
                      {label(ELIGIBILITY, data.eligibility.status)}
                    </Badge>
                  </Group>
                  {data.eligibility.reason_summary ? (
                    <Text size="sm">{data.eligibility.reason_summary}</Text>
                  ) : null}
                  {data.eligibility.status === "needs_review" ? (
                    <Alert color="orange" title="Perlu keputusanmu">
                      <Stack gap="sm" align="flex-start">
                        <Text size="sm">
                          Gawe belum bisa memastikan. Baca syaratnya di daftar lowongan, lalu
                          tentukan sendiri.
                        </Text>
                        <Button component={Link} to="/matches" variant="light">
                          Periksa syarat lowongan
                        </Button>
                      </Stack>
                    </Alert>
                  ) : null}
                  {data.eligibility.status === "ineligible" ? (
                    <Alert color="red" title="Tidak sesuai syarat">
                      Dokumen lamaran tidak dibuat untuk lowongan yang tidak sesuai syarat. Kamu
                      tetap bisa membuka halaman resminya kalau ingin melamar sendiri.
                    </Alert>
                  ) : null}
                </>
              ) : (
                <Text size="sm" c="dimmed">
                  Syarat lowongan belum diperiksa.
                </Text>
              )}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Seberapa cocok</Title>
              {data.fit ? (
                <>
                  <Group justify="space-between">
                    <Text size="sm">
                      {data.fit.fit_score} dari 100 · {label(FIT_VERDICT, data.fit.verdict)}
                    </Text>
                  </Group>
                  <Progress value={data.fit.fit_score} color="indigo" size="lg" radius="xl" />
                </>
              ) : (
                <Text size="sm" c="dimmed">
                  Kecocokan belum dihitung. Gawe menghitungnya setelah syarat lowongan jelas.
                </Text>
              )}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="md">
              <div>
                <Title order={3}>Dokumen lamaran</Title>
                <Text size="sm" c="dimmed">
                  CV dan surat lamaran dibuat dari CV Utama milikmu. Gawe tidak menambahkan
                  pengalaman atau keahlian yang tidak kamu miliki.
                </Text>
              </div>

              {eligible ? (
                <Group>
                  <Button
                    loading={busyKind === "cv"}
                    disabled={busyKind !== null && busyKind !== "cv"}
                    onClick={() => {
                      setPendingKind("cv");
                      void generate.mutateAsync({
                        applicationId: data.application_id,
                        kinds: ["cv"],
                        language: "en",
                      });
                    }}
                  >
                    Buat CV untuk lowongan ini
                  </Button>
                  <Button
                    variant="light"
                    loading={busyKind === "cover_letter"}
                    disabled={busyKind !== null && busyKind !== "cover_letter"}
                    onClick={() => {
                      setPendingKind("cover_letter");
                      void generate.mutateAsync({
                        applicationId: data.application_id,
                        kinds: ["cover_letter"],
                        language: "en",
                      });
                    }}
                  >
                    Buat surat lamaran
                  </Button>
                </Group>
              ) : (
                <Text size="sm" c="dimmed">
                  Pembuatan dokumen tersedia setelah lowongan dinyatakan sesuai syarat.
                </Text>
              )}
              {generate.isError ? (
                <Alert color="red" title="Dokumen belum jadi">
                  {friendlyError(generate.error)}
                </Alert>
              ) : null}

              {documents.length === 0 ? (
                <Alert color="gray" title="Belum ada dokumen">
                  <Text size="sm">
                    Tekan salah satu tombol di atas. Setelah selesai, kamu bisa membaca dan
                    memeriksanya di sini sebelum diunduh.
                  </Text>
                </Alert>
              ) : (
                <Table.ScrollContainer minWidth={560}>
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Jenis</Table.Th>
                        <Table.Th>Versi</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th>Pemeriksaan</Table.Th>
                        <Table.Th />
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {documents.map((document) => (
                        <Table.Tr key={document.document_version_id}>
                          <Table.Td>
                            <Text size="sm" fw={500}>
                              {document.kind === "cv" ? "CV" : "Surat lamaran"}
                            </Text>
                          </Table.Td>
                          <Table.Td>Ke-{document.version}</Table.Td>
                          <Table.Td>
                            <Badge
                              variant="light"
                              color={document.approved ? "teal" : "gray"}
                              mr={document.approved ? 6 : 0}
                            >
                              {label(DOCUMENT_STATUS, document.status)}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="sm">{label(REVIEW_STATUS, document.review_status)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Button
                              variant="light"
                              size="compact-sm"
                              onClick={() => setSelected(document.document_version_id)}
                            >
                              Baca
                            </Button>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}

              {selected ? (
                <DocumentReviewPanel
                  applicationId={data.application_id}
                  documentVersionId={selected}
                  onClose={() => setSelected(null)}
                />
              ) : null}
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Unduh dokumen</Title>
              <Text size="sm" c="dimmed">
                Hanya dokumen yang sudah kamu setujui yang bisa diunduh.
              </Text>
              <Stack gap={4}>
                <Text size="sm">{`CV: ${data.suggested_filenames.cv}`}</Text>
                <Text size="sm">{`Surat lamaran: ${data.suggested_filenames.cover_letter}`}</Text>
                <Text size="sm" c="dimmed">
                  {approvedCv && approvedCoverLetter
                    ? "Keduanya sudah disetujui dan siap diunduh."
                    : approvedCv
                      ? "CV sudah disetujui. Surat lamaran belum."
                      : approvedCoverLetter
                        ? "Surat lamaran sudah disetujui. CV belum."
                        : "Belum ada versi yang disetujui, jadi keduanya belum bisa diunduh."}
                </Text>
              </Stack>
              <Text size="sm" c="dimmed">
                Nama file diatur Gawe supaya rapi saat dikirim. Buka dokumen di atas untuk
                menyetujui atau mengunduhnya.
              </Text>
            </Stack>
          </Card>

          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Kirim lamaran</Title>
              {data.job.apply_url ? (
                <>
                  <Text size="sm">
                    Unduh dokumenmu, lalu kirim lewat halaman resmi perusahaan. Gawe tidak mengirim
                    lamaran otomatis.
                  </Text>
                  <Group>
                    <Button
                      component="a"
                      href={data.job.apply_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Buka halaman lamaran resmi
                    </Button>
                    <Button component={Link} to="/matches" variant="subtle">
                      Kembali ke daftar lowongan
                    </Button>
                  </Group>
                </>
              ) : (
                <Alert color="gray" title="Alamat lamaran tidak tersedia">
                  Sumber lowongan ini tidak menyediakan alamat lamaran resmi.
                </Alert>
              )}
            </Stack>
          </Card>

          <Divider />
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              Terakhir diperbarui {data.updated_at}
            </Text>
            <Button component={Link} to="/applications" variant="subtle">
              Semua lamaran
            </Button>
          </Group>
        </Stack>
      ) : null}
    </PageFrame>
  );
}
