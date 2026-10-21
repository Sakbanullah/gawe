import {
  Alert,
  Badge,
  Button,
  Divider,
  Group,
  Paper,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { useState } from "react";

import { ApiError, type DocumentVersion } from "../app/apiClient";
import {
  useApproveDocument,
  useCreateDocumentRevision,
  useDocumentFindings,
  useDocumentVersion,
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

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Aksi gagal.";
}

function format(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
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
  const [note, setNote] = useState("");
  const [summary, setSummary] = useState<string | null>(null);

  const data: DocumentVersion | undefined = version.data;
  const content = (data?.content ?? {}) as unknown as Content;
  const findings = useDocumentFindings(
    applicationId,
    documentVersionId,
    data?.review_status === "completed",
  );
  const diff = (data?.diff ?? {}) as { base?: string; items?: DiffItem[] };
  const missing = content.missing ?? [];
  const verdict = findings.data?.verdict;
  const canApprove =
    data?.review_status === "completed" &&
    (verdict === "pass" || verdict === "unresolved") &&
    !data?.approved;

  if (version.isError) {
    return (
      <Alert color="red" title="Dokumen gagal dimuat">
        {errorText(version.error)}
      </Alert>
    );
  }
  if (!data) {
    return <Text size="sm">Memuat versi dokumen…</Text>;
  }

  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={5}>
            {data.kind === "cv" ? "CV" : "Cover letter"} v{data.version}
          </Title>
          <Group gap="xs">
            <Badge variant="outline">{data.status}</Badge>
            <Badge variant="light">review: {data.review_status}</Badge>
            {data.approved ? <Badge color="green">approved</Badge> : null}
            <Button variant="subtle" size="xs" onClick={onClose}>
              Tutup
            </Button>
          </Group>
        </Group>
        <Text size="xs" c="dimmed">
          Hash {data.content_hash.slice(0, 12)} · {data.kind === "cv" ? "CV" : "CL"} ·
          approval terikat versi dan hash ini
        </Text>

        {missing.length > 0 ? (
          <Alert color="orange" title="Informasi belum tersedia">
            <Text size="sm">{missing.join(", ")}</Text>
            <Text size="xs" c="dimmed">
              Draft tidak mengarang data. Lengkapi profil lalu buat versi baru.
            </Text>
          </Alert>
        ) : null}

        <Divider label="Isi" labelPosition="left" />
        {content.kind === "cover_letter" ? (
          <Stack gap={6}>
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
          <Stack gap={6}>
            <Text fw={500}>{content.header?.full_name}</Text>
            <Text size="xs" c="dimmed">
              {[content.header?.email, content.header?.phone, content.header?.location]
                .filter(Boolean)
                .join(" · ")}
            </Text>
            {content.summary ? <Text size="sm">{content.summary.text}</Text> : null}
            {(content.skills ?? []).length > 0 ? (
              <Text size="sm">
                Skills: {(content.skills ?? []).map((skill) => skill.name).join(", ")}
              </Text>
            ) : null}
            {(content.experience ?? []).map((role, index) => (
              <Stack gap={2} key={index}>
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
              </Stack>
            ))}
            {(content.projects ?? []).map((project, index) => (
              <Text size="sm" key={index}>
                {project.name}: {project.description}
              </Text>
            ))}
            {(content.education ?? []).map((item, index) => (
              <Text size="sm" key={index}>
                {item.degree} · {item.institution}
              </Text>
            ))}
          </Stack>
        )}

        <Divider label="Diff" labelPosition="left" />
        <Text size="xs" c="dimmed">
          Basis: {diff.base === "document_version" ? "versi sebelumnya" : "Master CV"}
        </Text>
        <Table withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Path</Table.Th>
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
                    <Text size="xs">{item.path}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" variant="light">
                      {item.change}
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

        {data.review_status === "completed" ? (
          <>
            <Divider label="Findings" labelPosition="left" />
            <Group gap="xs">
              <Badge>{findings.data?.verdict ?? "belum ada"}</Badge>
              <Text size="sm">
                blocker{" "}
                {(findings.data?.findings ?? []).filter((item) => item.severity === "blocker").length} ·
                major{" "}
                {(findings.data?.findings ?? []).filter((item) => item.severity === "major").length}
              </Text>
            </Group>
            {(findings.data?.findings ?? []).map((finding) => (
              <Alert
                key={finding.finding_id}
                color={finding.severity === "blocker" ? "red" : "orange"}
                title={`${finding.severity}: ${finding.category}`}
              >
                <Text size="sm">{finding.problem}</Text>
                <Text size="xs" c="dimmed">
                  {finding.quote}
                </Text>
              </Alert>
            ))}
          </>
        ) : null}

        <Divider label="Aksi" labelPosition="left" />
        <Group>
          <Button
            variant="light"
            loading={review.isPending}
            disabled={data.review_status === "completed" || data.approved}
            onClick={() =>
              void review.mutateAsync({ applicationId, documentVersionId })
            }
          >
            Jalankan review
          </Button>
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
            Setujui versi ini
          </Button>
          <Button
            variant="light"
            color="orange"
            loading={approve.isPending}
            disabled={data.review_status !== "completed" || data.approved}
            onClick={() =>
              void approve.mutateAsync({
                applicationId,
                documentVersionId,
                contentHash: data.content_hash,
                decision: "changes_requested",
                note,
              })
            }
          >
            Minta perubahan
          </Button>
        </Group>
        <Textarea
          label="Catatan approval"
          maxLength={2000}
          minRows={2}
          value={note}
          onChange={(event) => setNote(event.currentTarget.value)}
        />

        {data.kind === "cv" && content.summary ? (
          <>
            <Divider label="Edit ringkasan" labelPosition="left" />
            <Textarea
              minRows={2}
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
          </>
        ) : null}

        {review.isError || approve.isError || revise.isError ? (
          <Alert color="red">
            {errorText(review.error ?? approve.error ?? revise.error)}
          </Alert>
        ) : null}
      </Stack>
    </Paper>
  );
}
