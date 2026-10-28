import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { useEffect, useState } from "react";

import { documentPdfUrl, exportDownloadUrl, type DocumentVersion } from "../app/apiClient";
import { friendlyError } from "../app/errors";
import {
  DIFF_CHANGE,
  DOCUMENT_STATUS,
  FINDING_SEVERITY,
  REVIEW_STATUS,
  diffPathLabel,
  fieldLabel,
  label,
} from "../app/labels";
import {
  useApproveDocument,
  useCreateDocumentRevision,
  useCreateExport,
  useDocumentFindings,
  useDocumentVersion,
  useExports,
  useRequestDocumentRevision,
  useRunDocumentReview,
} from "../app/queries";

type Content = {
  kind?: string;
  language?: string;
  header?: {
    full_name?: string | null;
    email?: string | null;
    phone?: string | null;
    location?: string | null;
    links?: string[];
  };
  summary?: { text?: string } | null;
  skills?: { name?: string }[];
  experience?: {
    company?: string;
    title?: string;
    start?: string | null;
    end?: string | null;
    bullets?: { id?: string; text?: string }[];
  }[];
  projects?: { name?: string; description?: string | null }[];
  education?: { institution?: string; degree?: string | null }[];
  certifications?: { name?: string }[];
  languages?: { name?: string }[];
  greeting?: string;
  paragraphs?: { text?: string }[];
  signoff?: string;
  signature?: string | null;
  missing?: string[];
};

type DiffItem = {
  path?: string;
  change?: string;
  before?: unknown;
  after?: unknown;
};

function format(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  // Structured values are flattened: raw JSON would read as noise to a person.
  if (Array.isArray(value)) return value.map(format).join(", ");
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>).map(format).join(" · ");
  }
  return String(value);
}

/** Missing profile fields are named the way a person sees them. */
function missingLabel(path: string): string {
  const parts = path.split(".");
  return parts.length === 1 ? fieldLabel(parts[0]) : fieldLabel(parts[parts.length - 1]);
}

export function DocumentReviewPanel({
  applicationId,
  documentVersionId,
  onClose,
}: {
  applicationId: string;
  documentVersionId: string;
  onClose: () => void;
}) {
  const version = useDocumentVersion(applicationId, documentVersionId);
  const review = useRunDocumentReview();
  const approve = useApproveDocument();
  const revise = useCreateDocumentRevision();
  const requestRevision = useRequestDocumentRevision();
  const exportDocument = useCreateExport();
  const exports = useExports(applicationId);
  const [note, setNote] = useState("");
  const [summary, setSummary] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  const data: DocumentVersion | undefined = version.data;
  const content = (data?.content ?? {}) as unknown as Content;
  const findings = useDocumentFindings(
    applicationId,
    documentVersionId,
    data?.review_status === "completed",
  );
  const allFindings = findings.data?.findings ?? [];
  const actionable = allFindings.filter(
    (item) => item.severity === "blocker" || item.severity === "major",
  );

  // Default to the ones the gate really blocks on; nothing is preselected when
  // the review has no actionable finding yet.
  useEffect(() => {
    setSelected(actionable.map((item) => item.finding_id));
  }, [findings.data]);

  function toggleFinding(findingId: string) {
    setSelected((current) =>
      current.includes(findingId)
        ? current.filter((item) => item !== findingId)
        : [...current, findingId],
    );
  }

  const diff = (data?.diff ?? {}) as { base?: string; items?: DiffItem[] };
  const missing = content.missing ?? [];
  const verdict = findings.data?.verdict;
  const canApprove =
    data?.review_status === "completed" &&
    (verdict === "pass" || verdict === "unresolved") &&
    !data?.approved;
  const approvedExports = (exports.data?.items ?? []).filter(
    (item) => item.document_version_id === documentVersionId,
  );

  if (version.isError) {
    return (
      <Alert color="red" title="Dokumen belum bisa dibuka">
        {friendlyError(version.error)}
      </Alert>
    );
  }
  if (!data) {
    return <Text size="sm">Sedang memuat dokumen…</Text>;
  }

  return (
    <Card withBorder>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <div>
            <Title order={3}>
              {data.kind === "cv" ? "CV" : "Surat lamaran"} versi ke-{data.version}
            </Title>
            <Group gap="xs" mt={4}>
              <Badge variant="light" color={data.approved ? "teal" : "gray"}>
                {label(DOCUMENT_STATUS, data.status)}
              </Badge>
              <Text size="xs" c="dimmed">
                {label(REVIEW_STATUS, data.review_status)}
              </Text>
            </Group>
          </div>
          <Button variant="subtle" onClick={onClose}>
            Tutup
          </Button>
        </Group>

        {missing.length > 0 ? (
          <Alert color="orange" title="Ada informasi yang belum ada di CV-mu">
            <Stack gap={4}>
              <Text size="sm">{missing.map(missingLabel).join(", ")}</Text>
              <Text size="xs" c="dimmed">
                Gawe tidak mengarang data. Lengkapi bagian ini di CV Utama, lalu buat versi baru.
              </Text>
              <Button
                size="compact-sm"
                variant="light"
                component="a"
                href="/master-cv"
                mt={4}
              >
                Lengkapi CV Utama
              </Button>
            </Stack>
          </Alert>
        ) : null}

        <Divider label="Isi dokumen" labelPosition="left" />
        {content.kind === "cover_letter" ? (
          <Stack gap={8}>
            <Text size="sm">{content.greeting}</Text>
            {(content.paragraphs ?? []).map((paragraph, index) => (
              <Text size="sm" key={index}>
                {paragraph.text}
              </Text>
            ))}
            <Text size="sm">{content.signoff}</Text>
            <Text size="sm">{content.signature}</Text>
          </Stack>
        ) : (
          <Stack gap={10}>
            <div>
              <Text fw={600}>{content.header?.full_name}</Text>
              <Text size="sm" c="dimmed">
                {[content.header?.email, content.header?.phone, content.header?.location]
                  .filter(Boolean)
                  .join(" · ")}
              </Text>
            </div>
            {content.summary ? <Text size="sm">{content.summary.text}</Text> : null}
            {(content.skills ?? []).length > 0 ? (
              <div>
                <Text size="sm" fw={600}>
                  Keahlian
                </Text>
                <Text size="sm">{(content.skills ?? []).map((skill) => skill.name).join(", ")}</Text>
              </div>
            ) : null}
            {(content.experience ?? []).length > 0 ? (
              <div>
                <Text size="sm" fw={600}>
                  Pengalaman kerja
                </Text>
                <Stack gap={8} mt={4}>
                  {(content.experience ?? []).map((role, index) => (
                    <div key={index}>
                      <Text size="sm" fw={500}>
                        {role.title} · {role.company}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {[role.start, role.end].filter(Boolean).join(" – ")}
                      </Text>
                      {(role.bullets ?? []).map((bullet) => (
                        <Text size="sm" key={bullet.id}>
                          • {bullet.text}
                        </Text>
                      ))}
                    </div>
                  ))}
                </Stack>
              </div>
            ) : null}
            {(content.projects ?? []).length > 0 ? (
              <div>
                <Text size="sm" fw={600}>
                  Proyek
                </Text>
                {(content.projects ?? []).map((project, index) => (
                  <Text size="sm" key={index}>
                    {project.name}: {project.description}
                  </Text>
                ))}
              </div>
            ) : null}
            {(content.education ?? []).length > 0 ? (
              <div>
                <Text size="sm" fw={600}>
                  Pendidikan
                </Text>
                {(content.education ?? []).map((item, index) => (
                  <Text size="sm" key={index}>
                    {item.degree} · {item.institution}
                  </Text>
                ))}
              </div>
            ) : null}
          </Stack>
        )}

        <Accordion variant="contained">
          <Accordion.Item value="changes">
            <Accordion.Control>Lihat apa yang diubah dari CV Utama</Accordion.Control>
            <Accordion.Panel>
              <Stack gap="sm">
                <Text size="xs" c="dimmed">
                  Dibandingkan dengan{" "}
                  {diff.base === "document_version" ? "versi sebelumnya" : "CV Utama"}.
                </Text>
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Bagian</Table.Th>
                      <Table.Th>Perubahan</Table.Th>
                      <Table.Th>Sebelum</Table.Th>
                      <Table.Th>Sesudah</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(diff.items ?? []).length === 0 ? (
                      <Table.Tr>
                        <Table.Td colSpan={4}>
                          <Text size="sm" c="dimmed">
                            Tidak ada perubahan.
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ) : (
                      (diff.items ?? []).map((item, index) => (
                        <Table.Tr key={`${item.path}-${index}`}>
                          <Table.Td>
                            <Text size="sm">{diffPathLabel(item.path)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Badge size="sm" variant="light" color="gray">
                              {label(DIFF_CHANGE, item.change)}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{format(item.before)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{format(item.after)}</Text>
                          </Table.Td>
                        </Table.Tr>
                      ))
                    )}
                  </Table.Tbody>
                </Table>
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>

        <Divider label="Pemeriksaan isi" labelPosition="left" />
        {data.review_status !== "completed" ? (
          <Stack gap="sm" align="flex-start">
            <Text size="sm">
              Periksa apakah dokumen ini hanya memakai fakta dari CV-mu, dan apakah panjangnya
              wajar.
            </Text>
            <Button
              loading={review.isPending}
              disabled={data.approved}
              onClick={() => void review.mutateAsync({ applicationId, documentVersionId })}
            >
              Periksa dokumen ini
            </Button>
          </Stack>
        ) : (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge variant="light" color={verdict === "pass" ? "teal" : "orange"}>
                {verdict === "pass"
                  ? "Tidak ada masalah"
                  : verdict === "changes_required"
                    ? "Ada yang perlu diperbaiki"
                    : "Perlu kamu putuskan"}
              </Badge>
            </Group>
            {allFindings.length === 0 ? (
              <Text size="sm" c="dimmed">
                Tidak ada temuan. Dokumen siap kamu setujui.
              </Text>
            ) : (
              <Stack gap="xs">
                <Text size="sm">
                  Centang temuan yang ingin diperbaiki. Gawe akan membuat versi baru.
                </Text>
                {allFindings.map((finding) => {
                  const checked = selected.includes(finding.finding_id);
                  return (
                    <Alert
                      key={finding.finding_id}
                      color={finding.severity === "blocker" ? "red" : "orange"}
                      title={label(FINDING_SEVERITY, finding.severity)}
                    >
                      <Checkbox
                        checked={checked}
                        onChange={() => toggleFinding(finding.finding_id)}
                        label={
                          <Text size="sm" fw={500}>
                            {finding.problem}
                          </Text>
                        }
                        description={finding.quote ?? undefined}
                      />
                    </Alert>
                  );
                })}
                <Group>
                  <Button
                    size="compact-sm"
                    variant="subtle"
                    onClick={() => setSelected(allFindings.map((item) => item.finding_id))}
                  >
                    Centang semua
                  </Button>
                  <Button size="compact-sm" variant="subtle" onClick={() => setSelected([])}>
                    Kosongkan
                  </Button>
                </Group>
                <Button
                  variant="light"
                  color="orange"
                  loading={requestRevision.isPending}
                  disabled={!selected.length || data.approved}
                  onClick={() =>
                    void requestRevision.mutateAsync({
                      applicationId,
                      documentVersionId,
                      contentHash: data.content_hash,
                      findingIds: selected,
                      note: note.trim() || undefined,
                    })
                  }
                >
                  Minta Gawe perbaiki yang dicentang
                </Button>
              </Stack>
            )}
          </Stack>
        )}

        <Divider label="Setujui dan unduh" labelPosition="left" />
        <Textarea
          label="Catatanmu (boleh dikosongkan)"
          description="Catatan ini tidak ikut tercetak di dokumen."
          maxLength={2000}
          minRows={2}
          value={note}
          onChange={(event) => setNote(event.currentTarget.value)}
        />
        <Group>
          <Button
            loading={approve.isPending}
            disabled={!canApprove}
            onClick={() =>
              void approve.mutateAsync({
                applicationId,
                documentVersionId,
                contentHash: data.content_hash,
                decision: "approved",
                note,
              })
            }
          >
            Setujui dokumen ini
          </Button>
          <Button
            component="a"
            href={documentPdfUrl(applicationId, documentVersionId)}
            target="_blank"
            rel="noreferrer"
            variant="light"
          >
            Lihat sebagai PDF
          </Button>
          <Button
            loading={exportDocument.isPending}
            disabled={!data.approved}
            onClick={() =>
              void exportDocument.mutateAsync({
                applicationId,
                body: {
                  kind: data.kind,
                  document_version_id: documentVersionId,
                  content_hash: data.content_hash,
                },
              })
            }
          >
            Siapkan PDF untuk diunduh
          </Button>
        </Group>
        {!canApprove && !data.approved ? (
          <Text size="xs" c="dimmed">
            Tombol setujui aktif setelah pemeriksaan isi selesai.
          </Text>
        ) : null}
        {data.approved ? (
          <Alert color="teal" title="Dokumen ini sudah disetujui">
            Kalau kamu mengubah isinya, versi baru perlu disetujui lagi.
          </Alert>
        ) : null}

        {approvedExports.length > 0 ? (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>File</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Halaman</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {approvedExports.map((item) => (
                <Table.Tr key={item.export_id}>
                  <Table.Td>
                    <Text size="sm">{item.filename}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="sm" color={item.status === "exported" ? "teal" : "orange"} variant="light">
                      {item.status === "exported" ? "Siap diunduh" : "Sedang disiapkan"}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {(item as { qa?: { page_count?: number } | null }).qa?.page_count ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {item.status === "exported" ? (
                      <Button
                        size="compact-sm"
                        variant="light"
                        component="a"
                        href={exportDownloadUrl(applicationId, item.export_id)}
                      >
                        Unduh PDF
                      </Button>
                    ) : (
                      <Text size="sm" c="dimmed">
                        Tunggu sebentar
                      </Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : null}

        {exportDocument.isError ? (
          <Alert color="red" title="PDF belum siap">
            {friendlyError(exportDocument.error)}
          </Alert>
        ) : null}

        {data.kind === "cv" && content.summary ? (
          <Accordion variant="contained">
            <Accordion.Item value="edit">
              <Accordion.Control>Ubah ringkasan CV ini</Accordion.Control>
              <Accordion.Panel>
                <Stack gap="sm">
                  <Textarea
                    label="Ringkasan"
                    description="Perubahan disimpan sebagai versi baru dan perlu disetujui ulang."
                    minRows={3}
                    value={summary ?? content.summary.text ?? ""}
                    onChange={(event) => setSummary(event.currentTarget.value)}
                  />
                  <Button
                    variant="light"
                    loading={revise.isPending}
                    onClick={() =>
                      void revise.mutateAsync({
                        applicationId,
                        documentVersionId,
                        baseContentHash: data.content_hash,
                        path: "summary.text",
                        value: summary ?? content.summary?.text ?? "",
                      })
                    }
                  >
                    Simpan sebagai versi baru
                  </Button>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        ) : null}

        {review.isError || approve.isError || revise.isError ? (
          <Alert color="red" title="Belum berhasil">
            {friendlyError(review.error ?? approve.error ?? revise.error)}
          </Alert>
        ) : null}
      </Stack>
    </Card>
  );
}

