import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";

import type { SourceRegistryEntry } from "../app/apiClient";
import { ApiError } from "../app/apiClient";
import { detailMessage, friendlyError } from "../app/errors";
import { HEALTH_STATUS, VERIFICATION_STATUS, label } from "../app/labels";
import { useCreateSource, useSources, useUpdateSource } from "../app/queries";
import { StatusBadge } from "./states";

const MARKETS = [
  { value: "global", label: "Luar negeri" },
  { value: "indonesia", label: "Indonesia" },
];
const ATS = [
  { value: "greenhouse", label: "Greenhouse" },
  { value: "lever", label: "Lever" },
  { value: "ashby", label: "Ashby" },
  { value: "unknown", label: "Lainnya" },
];
const VERIFICATION = Object.entries(VERIFICATION_STATUS).map(([value, text]) => ({
  value,
  label: text,
}));

/** Attaches a server field error to the input that caused it. */
function fieldError(error: unknown, field: string): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  const detail = error.details.find((item) => item.field === field);
  return detail ? detailMessage(detail) : undefined;
}

function CreateSourceForm() {
  const create = useCreateSource();
  const [company, setCompany] = useState("");
  const [careersUrl, setCareersUrl] = useState("");
  const [market, setMarket] = useState<string>("global");
  const [ats, setAts] = useState<string>("greenhouse");
  const [tosNotes, setTosNotes] = useState("");
  const [advanced, setAdvanced] = useState(false);

  const ready = company.trim().length > 0 && careersUrl.trim().length > 0;

  const resetError = () => {
    if (create.error) create.reset();
  };

  return (
    <Card withBorder>
      <Stack gap="sm">
        <div>
          <Title order={3}>Tambah perusahaan</Title>
          <Text size="sm" c="dimmed">
            Masukkan perusahaan yang ingin kamu pantau. Gawe hanya mengambil lowongan dari halaman
            karier resmi perusahaan.
          </Text>
        </div>
        <TextInput
          label="Nama perusahaan"
          placeholder="Contoh: Acme Indonesia"
          value={company}
          error={fieldError(create.error, "company")}
          onChange={(event) => {
            resetError();
            setCompany(event.currentTarget.value);
          }}
        />
        <TextInput
          label="Alamat halaman karier"
          description="Salin dari browser, misalnya https://boards.greenhouse.io/acme"
          placeholder="https://"
          value={careersUrl}
          error={fieldError(create.error, "careers_url")}
          onChange={(event) => {
            resetError();
            setCareersUrl(event.currentTarget.value);
          }}
        />
        <Group grow>
          <Select
            label="Lokasi perusahaan"
            data={MARKETS}
            value={market}
            onChange={(value) => {
              resetError();
              setMarket(value ?? "global");
            }}
          />
          <Select
            label="Jenis halaman karier"
            description="Kalau tidak tahu, pilih Lainnya."
            data={ATS}
            value={ats}
            onChange={(value) => {
              resetError();
              setAts(value ?? "unknown");
            }}
          />
        </Group>

        <Button variant="subtle" size="compact-sm" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? "Sembunyikan catatan tambahan" : "Tambah catatan (opsional)"}
        </Button>
        {advanced ? (
          <Textarea
            label="Catatan tentang izin pengambilan data"
            description="Opsional. Berguna kalau kamu ingin mencatat aturan pemakaian dari situs itu."
            autosize
            minRows={2}
            value={tosNotes}
            onChange={(event) => {
              resetError();
              setTosNotes(event.currentTarget.value);
            }}
          />
        ) : null}

        {create.error ? (
          <Alert color="red" title="Belum bisa ditambahkan">
            {friendlyError(create.error)}
          </Alert>
        ) : null}
        {create.isSuccess ? (
          <Alert color="teal" title="Perusahaan ditambahkan">
            Perusahaan ini belum aktif. Cek dulu alamatnya, lalu aktifkan di daftar bawah.
          </Alert>
        ) : null}

        <Group>
          <Button
            disabled={!ready || create.isPending}
            loading={create.isPending}
            onClick={() =>
              create.mutate(
                {
                  company: company.trim(),
                  careers_url: careersUrl.trim(),
                  market: market as "indonesia" | "global",
                  ats: ats as "greenhouse" | "lever" | "ashby" | "unknown",
                  access_method: "ats_api",
                  tos_notes: tosNotes.trim() || undefined,
                  enabled: false,
                  priority_order: 100,
                  fetch_interval_minutes: 360,
                  daily_request_quota: 24,
                },
                {
                  onSuccess: () => {
                    setCompany("");
                    setCareersUrl("");
                    setTosNotes("");
                  },
                },
              )
            }
          >
            Tambah perusahaan
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function EditSourceModal({
  source,
  onClose,
}: {
  source: SourceRegistryEntry;
  onClose: () => void;
}) {
  const update = useUpdateSource();
  const [company, setCompany] = useState(source.company);
  const [careersUrl, setCareersUrl] = useState(source.careers_url);
  const [market, setMarket] = useState<string>(source.market);
  const [ats, setAts] = useState<string>(source.ats);
  const [verification, setVerification] = useState<string>(source.verification_status);
  const [enabled, setEnabled] = useState(source.enabled);
  const [priority, setPriority] = useState<number>(source.priority_order);
  const [interval, setInterval] = useState<number>(source.fetch_interval_minutes);
  const [quota, setQuota] = useState<number>(source.daily_request_quota);
  const [tosNotes, setTosNotes] = useState(source.tos_notes ?? "");
  const [dismissed, setDismissed] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const error = dismissed ? null : update.error;

  const resetError = () => {
    setDismissed(true);
    if (update.error) update.reset();
  };

  return (
    <Modal opened onClose={onClose} title={`Ubah ${source.company}`} size="lg">
      <Stack gap="sm">
        <TextInput
          label="Nama perusahaan"
          value={company}
          error={fieldError(error, "company")}
          onChange={(event) => {
            resetError();
            setCompany(event.currentTarget.value);
          }}
        />
        <TextInput
          label="Alamat halaman karier"
          value={careersUrl}
          error={fieldError(error, "careers_url")}
          onChange={(event) => {
            resetError();
            setCareersUrl(event.currentTarget.value);
          }}
        />
        <Group grow>
          <Select
            label="Lokasi perusahaan"
            data={MARKETS}
            value={market}
            error={fieldError(error, "market")}
            onChange={(value) => {
              resetError();
              setMarket(value ?? "global");
            }}
          />
          <Select
            label="Jenis halaman karier"
            data={ATS}
            value={ats}
            error={fieldError(error, "ats")}
            onChange={(value) => {
              resetError();
              setAts(value ?? "unknown");
            }}
          />
        </Group>
        <Select
          label="Status pemeriksaan"
          description="Pilih Sudah dicek setelah kamu memastikan alamatnya benar."
          data={VERIFICATION}
          value={verification}
          onChange={(value) => {
            resetError();
            setVerification(value ?? "unverified");
          }}
        />
        <Switch
          label="Ikut dicari saat pencarian lowongan"
          checked={enabled}
          onChange={(event) => {
            resetError();
            setEnabled(event.currentTarget.checked);
          }}
        />

        <Button variant="subtle" size="compact-sm" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? "Sembunyikan pengaturan lanjutan" : "Pengaturan lanjutan"}
        </Button>
        {advanced ? (
          <Stack gap="sm">
            <Group grow>
              <NumberInput
                label="Urutan pengecekan"
                description="Angka kecil dicek lebih dulu."
                min={1}
                max={1000}
                value={priority}
                error={fieldError(error, "priority_order")}
                onChange={(value) => {
                  resetError();
                  setPriority(typeof value === "number" ? value : 100);
                }}
              />
              <NumberInput
                label="Jeda antar pengecekan (menit)"
                min={5}
                max={43200}
                value={interval}
                error={fieldError(error, "fetch_interval_minutes")}
                onChange={(value) => {
                  resetError();
                  setInterval(typeof value === "number" ? value : 360);
                }}
              />
              <NumberInput
                label="Batas permintaan per hari"
                description="0 berarti tanpa batas."
                min={0}
                max={100000}
                value={quota}
                error={fieldError(error, "daily_request_quota")}
                onChange={(value) => {
                  resetError();
                  setQuota(typeof value === "number" ? value : 24);
                }}
              />
            </Group>
            <Textarea
              label="Catatan tentang izin pengambilan data"
              autosize
              minRows={2}
              value={tosNotes}
              onChange={(event) => {
                resetError();
                setTosNotes(event.currentTarget.value);
              }}
            />
          </Stack>
        ) : null}

        {error ? (
          <Alert color="red" title="Belum bisa disimpan">
            {friendlyError(error)}
          </Alert>
        ) : null}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Batal
          </Button>
          <Button
            loading={update.isPending}
            onClick={() => {
              setDismissed(false);
              update.mutate(
                {
                  sourceId: source.source_id,
                  body: {
                    company: company.trim(),
                    careers_url: careersUrl.trim(),
                    market: market as "indonesia" | "global",
                    ats: ats as SourceRegistryEntry["ats"],
                    verification_status: verification as SourceRegistryEntry["verification_status"],
                    enabled,
                    priority_order: priority,
                    fetch_interval_minutes: interval,
                    daily_request_quota: quota,
                    tos_notes: tosNotes.trim(),
                  },
                },
                { onSuccess: onClose },
              );
            }}
          >
            Simpan perubahan
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function SourceRegistry({ editable = false }: { editable?: boolean }) {
  const sources = useSources();
  const update = useUpdateSource();
  const [editing, setEditing] = useState<SourceRegistryEntry | null>(null);

  if (sources.isPending) {
    return <Text c="dimmed">Sedang memuat daftar perusahaan…</Text>;
  }
  if (sources.isError) {
    return (
      <Alert color="red" title="Daftar perusahaan belum bisa dimuat">
        <Button variant="light" color="red" mt="xs" onClick={() => void sources.refetch()}>
          Coba lagi
        </Button>
      </Alert>
    );
  }

  const items = sources.data?.items ?? [];

  return (
    <Stack gap="md">
      <Card withBorder>
        <Stack gap="md">
          <div>
            <Title order={3}>Perusahaan yang dipantau</Title>
            <Text size="sm" c="dimmed">
              Lowongan hanya diambil dari perusahaan di daftar ini. Semua lewat halaman karier
              resmi.
            </Text>
          </div>
          {items.length === 0 ? (
            <Alert color="gray" title="Belum ada perusahaan">
              <Text size="sm">
                Tambahkan perusahaan pertama di bawah. Tanpa perusahaan, pencarian tidak akan
                menemukan lowongan.
              </Text>
            </Alert>
          ) : (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Perusahaan</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Lowongan tersimpan</Table.Th>
                  <Table.Th>Ikut dicari</Table.Th>
                  {editable ? <Table.Th /> : null}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {items.map((source) => (
                  <Table.Tr key={source.source_id}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {source.company}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {source.market === "indonesia" ? "Indonesia" : "Luar negeri"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <StatusBadge
                          status={source.verification_status}
                          label={label(VERIFICATION_STATUS, source.verification_status)}
                        />
                        {source.health_status !== "healthy" ? (
                          <Text size="xs" c="dimmed">
                            {label(HEALTH_STATUS, source.health_status)}
                            {source.consecutive_failures > 0
                              ? ` · gagal ${source.consecutive_failures}× berturut-turut`
                              : ""}
                          </Text>
                        ) : null}
                      </Stack>
                    </Table.Td>
                    <Table.Td>{source.job_count ?? 0}</Table.Td>
                    <Table.Td>{source.enabled ? "Ya" : "Tidak"}</Table.Td>
                    {editable ? (
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          <Button
                            size="compact-sm"
                            variant="light"
                            onClick={() => setEditing(source)}
                          >
                            Ubah
                          </Button>
                          <Button
                            size="compact-sm"
                            variant="subtle"
                            disabled={update.isPending}
                            onClick={() =>
                              update.mutate({
                                sourceId: source.source_id,
                                body: { enabled: !source.enabled },
                              })
                            }
                          >
                            {source.enabled ? "Jangan dicari" : "Ikutkan pencarian"}
                          </Button>
                        </Group>
                      </Table.Td>
                    ) : null}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {update.error ? (
            <Alert color="red" title="Perubahan belum tersimpan">
              {friendlyError(update.error)}
            </Alert>
          ) : null}
        </Stack>
      </Card>
      {editable ? <CreateSourceForm /> : null}
      {editing ? <EditSourceModal source={editing} onClose={() => setEditing(null)} /> : null}
    </Stack>
  );
}

