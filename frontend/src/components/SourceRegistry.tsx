import { useState } from "react";
import {
  Alert,
  Anchor,
  Badge,
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
} from "@mantine/core";

import type { SourceRegistryEntry } from "../app/apiClient";
import { ApiError } from "../app/apiClient";
import { useCreateSource, useSources, useUpdateSource } from "../app/queries";

const MARKETS = [
  { value: "global", label: "Global" },
  { value: "indonesia", label: "Indonesia" },
];
const ATS = [
  { value: "greenhouse", label: "Greenhouse" },
  { value: "lever", label: "Lever" },
  { value: "ashby", label: "Ashby" },
  { value: "himalayas", label: "Himalayas" },
  { value: "unknown", label: "Lainnya" },
];
const ACCESS = [
  { value: "ats_api", label: "ATS API" },
  { value: "aggregator", label: "Aggregator" },
];
const VERIFICATION = [
  { value: "unverified", label: "unverified" },
  { value: "verified", label: "verified" },
  { value: "restricted", label: "restricted" },
  { value: "broken", label: "broken" },
];

const VERIFICATION_COLOR: Record<string, string> = {
  verified: "green",
  unverified: "gray",
  restricted: "orange",
  broken: "red",
};

const HEALTH_COLOR: Record<string, string> = {
  healthy: "green",
  unknown: "gray",
  degraded: "orange",
  broken: "red",
};

function errorText(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
}

function fieldError(error: unknown, field: string): string | undefined {
  if (!(error instanceof ApiError)) {
    return undefined;
  }
  return error.details.find((detail) => detail.field === field)?.message;
}

function CreateSourceForm() {
  const create = useCreateSource();
  const [company, setCompany] = useState("");
  const [careersUrl, setCareersUrl] = useState("");
  const [market, setMarket] = useState<string>("global");
  const [ats, setAts] = useState<string>("greenhouse");
  const [accessMethod, setAccessMethod] = useState<string>("ats_api");
  const [tosNotes, setTosNotes] = useState("");

  const ready = company.trim().length > 0 && careersUrl.trim().length > 0;

  const resetError = () => {
    if (create.error) {
      create.reset();
    }
  };

  return (
    <Stack gap="xs">
      <Text fw={500}>Tambah sumber</Text>
      <Text size="sm" c="dimmed">
        Sumber baru selalu `unverified`. Verifikasi dan aktifkan setelah URL dicek.
      </Text>
      <Group grow align="flex-end">
        <TextInput
          label="Perusahaan"
          value={company}
          error={fieldError(create.error, "company")}
          onChange={(event) => {
            resetError();
            setCompany(event.currentTarget.value);
          }}
        />
        <TextInput
          label="Careers URL"
          placeholder="https://boards.greenhouse.io/..."
          value={careersUrl}
          error={fieldError(create.error, "careers_url")}
          onChange={(event) => {
            resetError();
            setCareersUrl(event.currentTarget.value);
          }}
        />
      </Group>
      <Group grow>
        <Select
          label="Market"
          data={MARKETS}
          value={market}
          onChange={(value) => {
            resetError();
            setMarket(value ?? "global");
          }}
        />
        <Select
          label="ATS"
          data={ATS}
          value={ats}
          onChange={(value) => {
            resetError();
            setAts(value ?? "unknown");
          }}
        />
        <Select
          label="Akses"
          data={ACCESS}
          value={accessMethod}
          onChange={(value) => {
            resetError();
            setAccessMethod(value ?? "ats_api");
          }}
        />
      </Group>
      <Textarea
        label="Catatan ToS"
        autosize
        minRows={2}
        value={tosNotes}
        onChange={(event) => {
          resetError();
          setTosNotes(event.currentTarget.value);
        }}
      />
      {create.error ? <Alert color="red">{errorText(create.error)}</Alert> : null}
      <Group>
        <Button
          disabled={!ready || create.isPending}
          onClick={() =>
            create.mutate({
              company: company.trim(),
              careers_url: careersUrl.trim(),
              market: market as "indonesia" | "global",
              ats: ats as "greenhouse" | "lever" | "ashby" | "himalayas" | "unknown",
              access_method: accessMethod as "ats_api" | "aggregator",
              tos_notes: tosNotes.trim() || undefined,
              enabled: false,
              priority_order: 100,
              fetch_interval_minutes: 360,
              daily_request_quota: 24,
            })
          }
        >
          Tambah sumber
        </Button>
      </Group>
    </Stack>
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
  const [accessMethod, setAccessMethod] = useState<string>(source.access_method);
  const [verification, setVerification] = useState<string>(source.verification_status);
  const [enabled, setEnabled] = useState(source.enabled);
  const [priority, setPriority] = useState<number>(source.priority_order);
  const [interval, setInterval] = useState<number>(source.fetch_interval_minutes);
  const [quota, setQuota] = useState<number>(source.daily_request_quota);
  const [tosNotes, setTosNotes] = useState(source.tos_notes ?? "");
  const [dismissed, setDismissed] = useState(false);
  const error = dismissed ? null : update.error;

  const resetError = () => {
    setDismissed(true);
    if (update.error) {
      update.reset();
    }
  };

  return (
    <Modal opened onClose={onClose} title={`Edit ${source.company}`}>
      <Stack gap="xs">
        <TextInput
          label="Perusahaan"
          value={company}
          error={fieldError(error, "company")}
          onChange={(event) => {
            resetError();
            setCompany(event.currentTarget.value);
          }}
        />
        <TextInput
          label="Careers URL"
          value={careersUrl}
          error={fieldError(error, "careers_url")}
          onChange={(event) => {
            resetError();
            setCareersUrl(event.currentTarget.value);
          }}
        />
        <Group grow>
          <Select
            label="Market"
            data={MARKETS}
            value={market}
            error={fieldError(error, "market")}
            onChange={(value) => {
              resetError();
              setMarket(value ?? "global");
            }}
          />
          <Select
            label="ATS"
            data={ATS}
            value={ats}
            error={fieldError(error, "ats")}
            onChange={(value) => {
              resetError();
              setAts(value ?? "unknown");
            }}
          />
          <Select
            label="Akses"
            data={ACCESS}
            value={accessMethod}
            error={fieldError(error, "access_method")}
            onChange={(value) => {
              resetError();
              setAccessMethod(value ?? "ats_api");
            }}
          />
        </Group>
        <Select
          label="Status verifikasi"
          data={VERIFICATION}
          value={verification}
          onChange={(value) => {
            resetError();
            setVerification(value ?? "unverified");
          }}
        />
        <Switch
          label="Aktif"
          checked={enabled}
          onChange={(event) => {
            resetError();
            setEnabled(event.currentTarget.checked);
          }}
        />
        <Group grow>
          <NumberInput
            label="Prioritas"
            description="Kecil dijalankan lebih dulu"
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
            label="Interval (menit)"
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
            label="Kuota 24 jam"
            description="0 = tanpa batas"
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
          label="Catatan ToS"
          autosize
          minRows={2}
          value={tosNotes}
          onChange={(event) => {
            resetError();
            setTosNotes(event.currentTarget.value);
          }}
        />
        {error ? <Alert color="red">{errorText(error)}</Alert> : null}
        <Group justify="flex-end">
          <Button variant="light" onClick={onClose}>
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
                    // A legacy row may still hold `html`, which the request
                    // contract no longer accepts. Sending it back unchanged would
                    // make the row unsavable, so only a real change is sent.
                    ...(accessMethod === source.access_method
                      ? {}
                      : { access_method: accessMethod as "ats_api" | "aggregator" }),
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
            Simpan
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
    return <Text c="dimmed">Memuat sumber…</Text>;
  }
  if (sources.isError) {
    return (
      <Alert color="red" title="Gagal memuat sumber">
        <Button variant="light" onClick={() => void sources.refetch()}>
          Coba lagi
        </Button>
      </Alert>
    );
  }

  const items = sources.data?.items ?? [];

  return (
    <Card withBorder>
      <Stack gap="md">
        <Text fw={500}>Sumber lowongan</Text>
        {items.length === 0 ? (
          <Alert color="gray">Belum ada sumber terdaftar.</Alert>
        ) : (
          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Perusahaan</Table.Th>
                <Table.Th>ATS</Table.Th>
                <Table.Th>Verifikasi</Table.Th>
                <Table.Th>Kesehatan</Table.Th>
                <Table.Th>Aktif</Table.Th>
                <Table.Th>Terakhir dicek</Table.Th>
                <Table.Th>Kuota 24 jam</Table.Th>
                <Table.Th>Job</Table.Th>
                {editable ? <Table.Th>Aksi</Table.Th> : null}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((source) => (
                <Table.Tr key={source.source_id}>
                  <Table.Td>{source.company}</Table.Td>
                  <Table.Td>{source.ats}</Table.Td>
                  <Table.Td>
                    <Badge color={VERIFICATION_COLOR[source.verification_status] ?? "gray"}>
                      {source.verification_status}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={HEALTH_COLOR[source.health_status] ?? "gray"}>
                      {source.health_status}
                    </Badge>
                    {source.consecutive_failures > 0 ? (
                      <Text size="xs" c="dimmed">
                        {source.consecutive_failures} gagal berturut-turut
                      </Text>
                    ) : null}
                  </Table.Td>
                  <Table.Td>{source.enabled ? "ya" : "tidak"}</Table.Td>
                  <Table.Td>{source.last_checked_at ?? "—"}</Table.Td>
                  <Table.Td>
                    {source.requests_last_24h}/{source.daily_request_quota || "∞"}
                  </Table.Td>
                  <Table.Td>{source.job_count ?? 0}</Table.Td>
                  {editable ? (
                    <Table.Td>
                      <Group gap="xs">
                        <Button size="compact-sm" variant="light" onClick={() => setEditing(source)}>
                          Edit
                        </Button>
                        <Button
                          size="compact-sm"
                          variant="light"
                          color={source.enabled ? "red" : "green"}
                          disabled={update.isPending}
                          onClick={() =>
                            update.mutate({
                              sourceId: source.source_id,
                              body: { enabled: !source.enabled },
                            })
                          }
                        >
                          {source.enabled ? "Nonaktifkan" : "Aktifkan"}
                        </Button>
                      </Group>
                    </Table.Td>
                  ) : null}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
        {items.some((source) => source.ats === "himalayas") ? (
          <Text size="xs" c="dimmed">
            Data lowongan dari{" "}
            <Anchor href="https://himalayas.app" target="_blank" rel="noreferrer">
              Himalayas
            </Anchor>
            . Tautan melamar dibuka apa adanya.
          </Text>
        ) : null}
        {update.error ? <Alert color="red">{errorText(update.error)}</Alert> : null}
        {editable ? <CreateSourceForm /> : null}
        {editing ? <EditSourceModal source={editing} onClose={() => setEditing(null)} /> : null}
      </Stack>
    </Card>
  );
}
