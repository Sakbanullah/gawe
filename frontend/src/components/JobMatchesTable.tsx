import {
  Alert,
  Anchor,
  Badge,
  Button,
  Divider,
  Drawer,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router";

import { ApiError, type MatchDetail, type MatchItem } from "../app/apiClient";
import {
  useCreateApplication,
  useMatchDetail,
  useOverrideMatchTier,
} from "../app/queries";

/** A job that closed after the list was loaded is a state change, not a failure. */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === "job_not_open") {
    return "Lowongan sudah ditutup. Muat ulang daftar Matches.";
  }
  return error instanceof Error ? error.message : "Permintaan gagal.";
}

const TIER_LABEL: Record<string, string> = {
  P1: "P1 · Global onsite",
  P2: "P2 · Global remote",
  P3: "P3 · Indonesia remote",
  P4: "P4 · Indonesia onsite",
  unclassified: "Belum terklasifikasi",
};

const TIER_VALUES = ["P1", "P2", "P3", "P4", "unclassified"] as const;
type TierValue = (typeof TIER_VALUES)[number];

const TIER_OPTIONS = TIER_VALUES.map((value) => ({ value, label: TIER_LABEL[value] }));

function asTier(value: string | null): TierValue | null {
  return TIER_VALUES.includes(value as TierValue) ? (value as TierValue) : null;
}

const STATUS_COLOR: Record<string, string> = {
  eligible: "green",
  needs_review: "yellow",
  ineligible: "red",
};

const RESULT_COLOR: Record<string, string> = {
  met: "green",
  not_met: "red",
  unknown: "yellow",
};

/** Only gaps the reader can act on; other missing fields stay out of the UI. */
const COMPLETENESS_LABEL: Record<string, string> = {
  company_name: "Nama perusahaan dari slug",
  posted_at: "Tanggal posting tidak tersedia",
};

function completenessNotes(missing: string[] | undefined): string[] {
  return (missing ?? [])
    .map((field) => COMPLETENESS_LABEL[field])
    .filter((label): label is string => Boolean(label));
}

export function MatchStatusBadge({ status }: { status: string }) {
  return <Badge color={STATUS_COLOR[status] ?? "gray"}>{status}</Badge>;
}

export function FitBadge({ fit }: { fit: MatchItem["fit"] }) {
  if (!fit) return <Text size="sm" c="dimmed">—</Text>;
  return (
    <Badge color={fit.verdict === "strong" ? "green" : fit.verdict === "moderate" ? "blue" : "gray"}>
      {fit.fit_score} · {fit.verdict}
    </Badge>
  );
}

export function JobDetailDrawer({
  jobId,
  onClose,
}: {
  jobId: string | null;
  onClose: () => void;
}) {
  const detail = useMatchDetail(jobId);
  const override = useOverrideMatchTier();
  const createApplication = useCreateApplication();
  const navigate = useNavigate();
  const [tier, setTier] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const data: MatchDetail | undefined = detail.data;

  return (
    <Drawer
      opened={jobId !== null}
      onClose={onClose}
      position="right"
      size="xl"
      title="Detail lowongan"
    >
      {detail.isPending ? (
        <Group>
          <Loader size="sm" />
          <Text>Memuat detail…</Text>
        </Group>
      ) : null}
      {detail.isError ? (
        <Alert
          color="red"
          title={
            detail.error instanceof ApiError && detail.error.code === "job_not_open"
              ? "Lowongan sudah ditutup"
              : "Gagal memuat detail"
          }
        >
          {errorMessage(detail.error)}
        </Alert>
      ) : null}
      {data ? (
        <Stack gap="md">
          <div>
            <Title order={3}>{data.job_detail.job.title}</Title>
            <Text size="sm" c="dimmed">
              {data.job_detail.job.company} ·{" "}
              {data.job_detail.job.location?.raw ?? "lokasi tidak dicantumkan"}
            </Text>
            {completenessNotes(data.job_detail.job.completeness?.missing_fields).map((note) => (
              <Text key={note} size="xs" c="dimmed">
                {note}
              </Text>
            ))}
          </div>

          <Group gap="xs">
            <MatchStatusBadge status={data.eligibility.status} />
            <FitBadge fit={data.fit} />
            <Badge variant="light">
              {TIER_LABEL[data.job_detail.job.priority_tier] ?? data.job_detail.job.priority_tier}
            </Badge>
            <Badge variant="outline">{data.recommendation}</Badge>
          </Group>

          {data.status_outdated ? (
            <Alert color="orange" title="Analisis kedaluwarsa">
              Deskripsi lowongan berubah setelah analisis terakhir. Analisis ulang sebelum
              membuat dokumen.
            </Alert>
          ) : null}

          {data.eligibility.reason_summary ? (
            <Alert color="gray" title="Ringkasan eligibility">
              {data.eligibility.reason_summary}
            </Alert>
          ) : null}

          {data.application_id ? (
            <Group>
              <Button component="a" href={`/applications/${data.application_id}`}>
                Buka Application Workspace
              </Button>
              <Text size="xs" c="dimmed">
                Workspace sudah ada untuk lowongan ini.
              </Text>
            </Group>
          ) : (
            <Group>
              <Button
                variant="light"
                loading={createApplication.isPending}
                onClick={() =>
                  createApplication.mutate(data.job_detail.job.job_id, {
                    onSuccess: (created) =>
                      navigate(`/applications/${created.application_id}`),
                  })
                }
              >
                Buat Application Workspace
              </Button>
              <Text size="xs" c="dimmed">
                Eligibility dan fit ditampilkan di workspace. Dokumen belum tersedia.
              </Text>
            </Group>
          )}
          {createApplication.error ? (
            <Alert color="red">{errorMessage(createApplication.error)}</Alert>
          ) : null}

          {data.job_detail.job.apply_url ? (
            <Group>
              <Button
                component="a"
                href={data.job_detail.job.apply_url}
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

          <Divider label="Eligibility" labelPosition="left" />
          <Stack gap="sm">
            {data.eligibility.checks.map((check) => (
              <Stack key={check.requirement_id} gap={4}>
                <Group gap="xs">
                  <Badge color={RESULT_COLOR[check.result] ?? "gray"}>{check.result}</Badge>
                  <Text size="sm" fw={500}>
                    {check.category}
                  </Text>
                </Group>
                <Text size="sm" fs="italic">
                  “{check.job_quote}”
                </Text>
                <Text size="sm">{check.reason}</Text>
                {check.evidence_refs?.length ? (
                  <Text size="xs" c="dimmed">
                    Bukti profil: {check.evidence_refs.join(", ")}
                  </Text>
                ) : null}
              </Stack>
            ))}
          </Stack>

          {data.fit ? (
            <>
              <Divider label="Fit" labelPosition="left" />
              <Table withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Komponen</Table.Th>
                    <Table.Th>Bobot</Table.Th>
                    <Table.Th>Nilai</Table.Th>
                    <Table.Th>Kontribusi</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.fit.components.map((component) => (
                    <Table.Tr key={component.name}>
                      <Table.Td>{component.name}</Table.Td>
                      <Table.Td>{component.weight}</Table.Td>
                      <Table.Td>{component.value}</Table.Td>
                      <Table.Td>{component.contribution}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {data.fit.gaps.length > 0 ? (
                <Stack gap={4}>
                  <Text size="sm" fw={500}>
                    Gap
                  </Text>
                  {data.fit.gaps.map((gap) => (
                    <Text key={gap.requirement_id} size="sm">
                      {gap.description}
                    </Text>
                  ))}
                </Stack>
              ) : null}
            </>
          ) : null}

          <Divider label="Persyaratan" labelPosition="left" />
          <Stack gap={4}>
            {data.job_detail.requirements.length === 0 ? (
              <Text size="sm" c="dimmed">
                Tidak ada persyaratan tersimpan.
              </Text>
            ) : (
              data.job_detail.requirements.map((requirement) => (
                <Group key={requirement.requirement_id} gap="xs" align="flex-start">
                  <Badge variant="light">{requirement.kind}</Badge>
                  <Text size="sm" style={{ flex: 1 }}>
                    {requirement.text}
                  </Text>
                </Group>
              ))
            )}
          </Stack>

          <Divider label="Deskripsi" labelPosition="left" />
          {data.job_detail.description_truncated ? (
            <Alert color="yellow">
              Deskripsi dipotong pada batas ukuran kontrak. Buka halaman sumber untuk teks penuh.
            </Alert>
          ) : null}
          <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {data.job_detail.description_text || "Deskripsi tidak tersedia."}
          </Text>
          {data.job_detail.source.access_method === "aggregator" ? (
            <Text size="xs" c="dimmed">
              Data lowongan dari{" "}
              <Anchor href="https://himalayas.app" target="_blank" rel="noreferrer">
                Himalayas
              </Anchor>
              . Tautan melamar dibuka apa adanya.
            </Text>
          ) : null}

          <Divider label="Koreksi tier" labelPosition="left" />
          <Stack gap="xs">
            <Text size="sm">
              Koreksi tier hanya tie-breaker. Skor fit dan eligibility tidak berubah, dan urutan
              daftar baru berubah setelah ranking dihitung ulang.
            </Text>
            <Select
              label="Tier"
              placeholder={TIER_LABEL[data.job_detail.job.priority_tier]}
              data={[...TIER_OPTIONS, { value: "__clear__", label: "Hapus koreksi" }]}
              value={tier}
              onChange={setTier}
              clearable
            />
            <TextInput
              label="Alasan"
              description="Wajib saat mengisi tier."
              value={reason}
              onChange={(event) => setReason(event.currentTarget.value)}
            />
            {override.error ? (
              <Alert color="red">{errorMessage(override.error)}</Alert>
            ) : null}
            <Group>
              <Button
                loading={override.isPending}
                disabled={tier === null}
                onClick={() =>
                  override.mutate({
                    jobId: data.job_detail.job.job_id,
                    tier: tier === "__clear__" ? null : asTier(tier),
                    reason: tier === "__clear__" ? null : reason.trim() || null,
                  })
                }
              >
                Simpan koreksi
              </Button>
              {override.isSuccess ? (
                <Text size="sm" c="green">
                  Koreksi tersimpan.
                </Text>
              ) : null}
            </Group>
          </Stack>
        </Stack>
      ) : null}
    </Drawer>
  );
}

export function JobMatchesTable({
  items,
  onSelect,
}: {
  items: MatchItem[];
  onSelect: (jobId: string) => void;
}) {
  return (
    <Table highlightOnHover withTableBorder>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Judul</Table.Th>
          <Table.Th>Perusahaan</Table.Th>
          <Table.Th>Lokasi</Table.Th>
          <Table.Th>Eligibility</Table.Th>
          <Table.Th>Fit</Table.Th>
          <Table.Th>Prioritas</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((item) => (
          <Table.Tr
            key={item.job.job_id}
            style={{ cursor: "pointer" }}
            onClick={() => onSelect(item.job.job_id)}
          >
            <Table.Td>
              <Anchor
                component="button"
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(item.job.job_id);
                }}
              >
                {item.job.title}
              </Anchor>
            </Table.Td>
            <Table.Td>
              {item.job.company}
              {completenessNotes(item.job.completeness?.missing_fields).map((note) => (
                <Text key={note} size="xs" c="dimmed">
                  {note}
                </Text>
              ))}
            </Table.Td>
            <Table.Td>{item.job.location?.raw ?? "—"}</Table.Td>
            <Table.Td>
              <MatchStatusBadge status={item.eligibility.status} />
            </Table.Td>
            <Table.Td>
              <FitBadge fit={item.fit} />
            </Table.Td>
            <Table.Td>{TIER_LABEL[item.job.priority_tier] ?? item.job.priority_tier}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
