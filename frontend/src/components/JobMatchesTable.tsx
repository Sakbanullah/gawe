import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Divider,
  Drawer,
  Group,
  Loader,
  Progress,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router";

import type { MatchDetail, MatchItem } from "../app/apiClient";
import { friendlyError } from "../app/errors";
import {
  CHECK_CATEGORY,
  CHECK_RESULT,
  ELIGIBILITY,
  FIT_COMPONENT,
  FIT_VERDICT,
  RECOMMENDATION,
  TIER,
  WORK_MODE,
  label,
} from "../app/labels";
import {
  useCreateApplication,
  useMatchDetail,
  useOverrideMatchTier,
  useReviewEligibility,
} from "../app/queries";


const TIER_VALUES = ["P1", "P2", "P3", "P4", "unclassified"] as const;
type TierValue = (typeof TIER_VALUES)[number];

const TIER_OPTIONS = TIER_VALUES.map((value) => ({ value, label: TIER[value] }));

function asTier(value: string | null): TierValue | null {
  return TIER_VALUES.includes(value as TierValue) ? (value as TierValue) : null;
}

/** Only gaps the reader can act on; other missing fields stay out of the UI. */
const COMPLETENESS_LABEL: Record<string, string> = {
  company_name: "Nama perusahaan diambil dari alamat halaman",
  posted_at: "Tanggal tayang tidak tercantum",
  snippet_only: "Butuh deskripsi lengkap",
};

function completenessNotes(missing: string[] | undefined): string[] {
  return (missing ?? [])
    .map((field) => COMPLETENESS_LABEL[field])
    .filter((text): text is string => Boolean(text));
}

export function EligibilityBadge({ status }: { status: string }) {
  const color = status === "eligible" ? "teal" : status === "ineligible" ? "red" : "orange";
  return (
    <Badge color={color} variant="light">
      {label(ELIGIBILITY, status)}
    </Badge>
  );
}

export function FitBadge({ fit }: { fit: MatchItem["fit"] }) {
  if (!fit) {
    return (
      <Text size="sm" c="dimmed">
        Belum dihitung
      </Text>
    );
  }
  return (
    <Group gap={6} wrap="nowrap">
      <Text size="sm" fw={600}>
        {fit.fit_score}
      </Text>
      <Text size="sm" c="dimmed">
        {label(FIT_VERDICT, fit.verdict)}
      </Text>
    </Group>
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
  const review = useReviewEligibility();
  const createApplication = useCreateApplication();
  const navigate = useNavigate();
  const [tier, setTier] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [reviewReason, setReviewReason] = useState("");

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
          <Text>Sedang memuat…</Text>
        </Group>
      ) : null}
      {detail.isError ? (
        <Alert color="red" title="Lowongan belum bisa dibuka">
          {friendlyError(detail.error, "Lowongan ini mungkin sudah ditutup. Coba muat ulang daftar.")}
        </Alert>
      ) : null}
      {data ? (
        <Stack gap="lg">
          <div>
            <Title order={2}>{data.job_detail.job.title}</Title>
            <Text c="dimmed" mt={4}>
              {data.job_detail.job.company} ·{" "}
              {data.job_detail.job.location?.raw ?? "lokasi tidak dicantumkan"} ·{" "}
              {label(WORK_MODE, data.job_detail.job.work_mode)}
            </Text>
            {completenessNotes(data.job_detail.job.completeness?.missing_fields).map((note) => (
              <Text key={note} size="xs" c="dimmed" mt={2}>
                {note}
              </Text>
            ))}
          </div>

          <Group gap="xs">
            <EligibilityBadge status={data.eligibility.status} />
            <Badge variant="light" color="gray">
              {label(TIER, data.job_detail.job.priority_tier)}
            </Badge>
            <Badge variant="outline" color="indigo">
              {label(RECOMMENDATION, data.recommendation)}
            </Badge>
          </Group>

          {data.status_outdated ? (
            <Alert color="orange" title="Lowongan ini berubah">
              Isi lowongan berubah setelah terakhir diperiksa. Jalankan ulang analisis sebelum
              membuat dokumen.
            </Alert>
          ) : null}

          {data.application_id ? (
            <Card withBorder padding="md">
              <Group justify="space-between" wrap="wrap" gap="sm">
                <Text size="sm">Kamu sudah mulai menyiapkan lamaran untuk lowongan ini.</Text>
                <Button component="a" href={`/applications/${data.application_id}`}>
                  Buka lamaran
                </Button>
              </Group>
            </Card>
          ) : (
            <Card withBorder padding="md">
              <Group justify="space-between" wrap="wrap" gap="sm">
                <Text size="sm">
                  Siap menyiapkan CV dan surat lamaran untuk lowongan ini?
                </Text>
                <Button
                  loading={createApplication.isPending}
                  onClick={() =>
                    createApplication.mutate(data.job_detail.job.job_id, {
                      onSuccess: (created) =>
                        navigate(`/applications/${created.application_id}`),
                    })
                  }
                >
                  Siapkan lamaran
                </Button>
              </Group>
            </Card>
          )}
          {createApplication.error ? (
            <Alert color="red" title="Belum bisa dibuat">
              {friendlyError(createApplication.error)}
            </Alert>
          ) : null}

          {data.job_detail.job.apply_url ? (
            <Button
              component="a"
              href={data.job_detail.job.apply_url}
              target="_blank"
              rel="noopener noreferrer"
              variant="light"
            >
              Buka halaman lamaran resmi
            </Button>
          ) : (
            <Alert color="gray" title="Alamat lamaran tidak tersedia">
              Sumber lowongan ini tidak menyediakan alamat lamaran.
            </Alert>
          )}
          <Text size="xs" c="dimmed">
            Gawe tidak mengirim lamaran untukmu. Pengiriman tetap kamu lakukan sendiri di situs
            resmi perusahaan.
          </Text>

          <Divider label="Apakah kamu memenuhi syaratnya?" labelPosition="left" />
          {data.eligibility.reason_summary ? (
            <Text size="sm">{data.eligibility.reason_summary}</Text>
          ) : null}
          {data.eligibility.override_reason ? (
            <Alert color="indigo" title="Kamu sudah memutuskan sendiri">
              <Text size="sm">{data.eligibility.override_reason}</Text>
            </Alert>
          ) : null}
          {data.eligibility.status === "needs_review" && !data.eligibility.override_reason ? (
            <Alert color="orange" title="Perlu keputusanmu">
              <Stack gap="sm">
                <Text size="sm">
                  Gawe belum bisa memastikan. Baca syarat di bawah, lalu putuskan apakah kamu
                  memenuhi.
                </Text>
                <TextInput
                  label="Alasan keputusanmu"
                  placeholder="Contoh: saya punya 3 tahun pengalaman yang diminta."
                  value={reviewReason}
                  onChange={(event) => setReviewReason(event.currentTarget.value)}
                />
                <Group>
                  <Button
                    size="sm"
                    loading={review.isPending}
                    disabled={!reviewReason.trim()}
                    onClick={() =>
                      review.mutate({
                        jobId: jobId as string,
                        status: "eligible",
                        reason: reviewReason.trim(),
                      })
                    }
                  >
                    Saya memenuhi syarat
                  </Button>
                  <Button
                    size="sm"
                    color="red"
                    variant="light"
                    loading={review.isPending}
                    disabled={!reviewReason.trim()}
                    onClick={() =>
                      review.mutate({
                        jobId: jobId as string,
                        status: "ineligible",
                        reason: reviewReason.trim(),
                      })
                    }
                  >
                    Saya tidak memenuhi
                  </Button>
                </Group>
                {review.error ? (
                  <Alert color="red">{friendlyError(review.error)}</Alert>
                ) : null}
              </Stack>
            </Alert>
          ) : null}

          <Stack gap="sm">
            {data.eligibility.checks.map((check) => (
              <Stack key={check.requirement_id} gap={4}>
                <Group gap="xs">
                  <Badge
                    color={check.result === "met" ? "teal" : check.result === "not_met" ? "red" : "orange"}
                    variant="light"
                  >
                    {label(CHECK_RESULT, check.result)}
                  </Badge>
                  <Text size="sm" fw={500}>
                    {label(CHECK_CATEGORY, check.category)}
                  </Text>
                </Group>
                <Text size="sm" fs="italic">
                  “{check.job_quote}”
                </Text>
                <Text size="sm" c="dimmed">
                  {check.reason}
                </Text>
              </Stack>
            ))}
          </Stack>

          <Divider label="Seberapa cocok" labelPosition="left" />
          {data.fit ? (
            <Stack gap="sm">
              <Group gap="md">
                <div style={{ flex: 1 }}>
                  <Group justify="space-between" mb={6}>
                    <Text size="sm" fw={500}>
                      Skor kecocokan
                    </Text>
                    <Text size="sm">
                      {data.fit.fit_score} / 100 · {label(FIT_VERDICT, data.fit.verdict)}
                    </Text>
                  </Group>
                  <Progress value={data.fit.fit_score} color="indigo" size="lg" radius="xl" />
                </div>
              </Group>
              {data.fit.gaps.length > 0 ? (
                <Stack gap={4}>
                  <Text size="sm" fw={500}>
                    Yang belum kamu miliki
                  </Text>
                  {data.fit.gaps.map((gap) => (
                    <Text key={gap.requirement_id} size="sm">
                      • {gap.description}
                    </Text>
                  ))}
                </Stack>
              ) : (
                <Text size="sm" c="dimmed">
                  Tidak ada persyaratan penting yang belum terpenuhi.
                </Text>
              )}
              <Accordion variant="contained">
                <Accordion.Item value="rincian">
                  <Accordion.Control>Lihat rincian perhitungan</Accordion.Control>
                  <Accordion.Panel>
                    <Table>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Bagian</Table.Th>
                          <Table.Th>Bobot</Table.Th>
                          <Table.Th>Nilai</Table.Th>
                          <Table.Th>Kontribusi</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.fit.components.map((component) => (
                          <Table.Tr key={component.name}>
                            <Table.Td>
                              {label(FIT_COMPONENT, component.name)}
                            </Table.Td>
                            <Table.Td>{component.weight}</Table.Td>
                            <Table.Td>{component.value}</Table.Td>
                            <Table.Td>{component.contribution}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            </Stack>
          ) : (
            <Text size="sm" c="dimmed">
              Kecocokan belum bisa dihitung. Gawe menghitungnya setelah syarat lowongan jelas.
            </Text>
          )}

          <Divider label="Syarat dari lowongan" labelPosition="left" />
          <Stack gap={6}>
            {data.job_detail.requirements.length === 0 ? (
              <Text size="sm" c="dimmed">
                Lowongan ini tidak mencantumkan syarat yang bisa dibaca Gawe.
              </Text>
            ) : (
              data.job_detail.requirements.map((requirement) => (
                <Group key={requirement.requirement_id} gap="xs" align="flex-start" wrap="nowrap">
                  <Badge variant="light" color="gray">
                    {requirement.kind === "must_have" ? "Wajib" : "Nilai plus"}
                  </Badge>
                  <Text size="sm" style={{ flex: 1 }}>
                    {requirement.text}
                  </Text>
                </Group>
              ))
            )}
          </Stack>

          <Divider label="Isi lowongan" labelPosition="left" />
          {data.job_detail.description_truncated ? (
            <Alert color="yellow" title="Teks dipotong">
              Gawe hanya menyimpan sebagian teks karena batas ukuran. Buka halaman aslinya untuk
              membaca semuanya.
            </Alert>
          ) : null}
          <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {data.job_detail.description_text || "Deskripsi tidak tersedia."}
          </Text>

          <Accordion variant="contained">
            <Accordion.Item value="prioritas">
              <Accordion.Control>Ubah prioritas lowongan ini</Accordion.Control>
              <Accordion.Panel>
                <Stack gap="sm">
                  <Text size="sm" c="dimmed">
                    Prioritas hanya dipakai untuk mengurutkan daftar saat skor kecocokan sama.
                    Skor dan syarat tidak berubah.
                  </Text>
                  <Select
                    label="Prioritas"
                    placeholder={label(TIER, data.job_detail.job.priority_tier)}
                    data={[...TIER_OPTIONS, { value: "__clear__", label: "Kembalikan ke otomatis" }]}
                    value={tier}
                    onChange={setTier}
                    clearable
                  />
                  <TextInput
                    label="Alasan"
                    description="Wajib diisi saat memilih prioritas."
                    value={reason}
                    onChange={(event) => setReason(event.currentTarget.value)}
                  />
                  {override.error ? (
                    <Alert color="red">{friendlyError(override.error)}</Alert>
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
                      Simpan prioritas
                    </Button>
                    {override.isSuccess ? (
                      <Text size="sm" c="teal">
                        Tersimpan.
                      </Text>
                    ) : null}
                  </Group>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
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
    <Table.ScrollContainer minWidth={640}>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Lowongan</Table.Th>
            <Table.Th>Lokasi</Table.Th>
            <Table.Th>Syarat</Table.Th>
            <Table.Th>Kecocokan</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((item) => (
            <Table.Tr key={item.job.job_id} style={{ cursor: "pointer" }} onClick={() => onSelect(item.job.job_id)}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {item.job.title}
                </Text>
                <Text size="xs" c="dimmed">
                  {item.job.company}
                </Text>
                {completenessNotes(item.job.completeness?.missing_fields).map((note) => (
                  <Text key={note} size="xs" c="dimmed">
                    {note}
                  </Text>
                ))}
              </Table.Td>
              <Table.Td>
                <Text size="sm">{item.job.location?.raw ?? "—"}</Text>
                <Text size="xs" c="dimmed">
                  {label(WORK_MODE, item.job.work_mode)}
                </Text>
              </Table.Td>
              <Table.Td>
                <EligibilityBadge status={item.eligibility.status} />
              </Table.Td>
              <Table.Td>
                <FitBadge fit={item.fit} />
              </Table.Td>
              <Table.Td>
                <Button
                  size="compact-sm"
                  variant="light"
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(item.job.job_id);
                  }}
                >
                  Baca detail
                </Button>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}


