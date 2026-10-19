import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";

import type { SourceRegistryEntry } from "../app/apiClient";
import { useCreateSource, useSources, useUpdateSource } from "../app/queries";

const MARKETS = [
  { value: "global", label: "Global" },
  { value: "indonesia", label: "Indonesia" },
];
const ATS = [
  { value: "greenhouse", label: "Greenhouse" },
  { value: "lever", label: "Lever" },
  { value: "ashby", label: "Ashby" },
  { value: "unknown", label: "Lainnya" },
];
const ACCESS = [
  { value: "ats_api", label: "ATS API" },
  { value: "html", label: "Halaman karier (HTML)" },
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

function errorText(error: unknown): string | null {
  return error instanceof Error ? error.message : null;
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
          onChange={(event) => setCompany(event.currentTarget.value)}
        />
        <TextInput
          label="Careers URL"
          placeholder="https://boards.greenhouse.io/..."
          value={careersUrl}
          onChange={(event) => setCareersUrl(event.currentTarget.value)}
        />
      </Group>
      <Group grow>
        <Select label="Market" data={MARKETS} value={market} onChange={(value) => setMarket(value ?? "global")} />
        <Select label="ATS" data={ATS} value={ats} onChange={(value) => setAts(value ?? "unknown")} />
        <Select
          label="Akses"
          data={ACCESS}
          value={accessMethod}
          onChange={(value) => setAccessMethod(value ?? "ats_api")}
        />
      </Group>
      <Textarea
        label="Catatan ToS"
        autosize
        minRows={2}
        value={tosNotes}
        onChange={(event) => setTosNotes(event.currentTarget.value)}
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
              ats: ats as "greenhouse" | "lever" | "ashby" | "unknown",
              access_method: accessMethod as "ats_api" | "html",
              tos_notes: tosNotes.trim() || undefined,
              enabled: false,
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
  const [verification, setVerification] = useState<string>(source.verification_status);
  const [enabled, setEnabled] = useState(source.enabled);
  const [tosNotes, setTosNotes] = useState(source.tos_notes ?? "");

  return (
    <Modal opened onClose={onClose} title={`Edit ${source.company}`}>
      <Stack gap="xs">
        <TextInput
          label="Perusahaan"
          value={company}
          onChange={(event) => setCompany(event.currentTarget.value)}
        />
        <TextInput
          label="Careers URL"
          value={careersUrl}
          onChange={(event) => setCareersUrl(event.currentTarget.value)}
        />
        <Select
          label="Status verifikasi"
          data={VERIFICATION}
          value={verification}
          onChange={(value) => setVerification(value ?? "unverified")}
        />
        <Switch
          label="Aktif"
          checked={enabled}
          onChange={(event) => setEnabled(event.currentTarget.checked)}
        />
        <Textarea
          label="Catatan ToS"
          autosize
          minRows={2}
          value={tosNotes}
          onChange={(event) => setTosNotes(event.currentTarget.value)}
        />
        {update.error ? <Alert color="red">{errorText(update.error)}</Alert> : null}
        <Group justify="flex-end">
          <Button variant="light" onClick={onClose}>
            Batal
          </Button>
          <Button
            loading={update.isPending}
            onClick={() =>
              update.mutate(
                {
                  sourceId: source.source_id,
                  body: {
                    company: company.trim(),
                    careers_url: careersUrl.trim(),
                    verification_status: verification as SourceRegistryEntry["verification_status"],
                    enabled,
                    tos_notes: tosNotes.trim(),
                  },
                },
                { onSuccess: onClose },
              )
            }
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
                <Table.Th>Aktif</Table.Th>
                <Table.Th>Terakhir dicek</Table.Th>
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
                  <Table.Td>{source.enabled ? "ya" : "tidak"}</Table.Td>
                  <Table.Td>{source.last_checked_at ?? "—"}</Table.Td>
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
        {update.error ? <Alert color="red">{errorText(update.error)}</Alert> : null}
        {editable ? <CreateSourceForm /> : null}
        {update.error ? <Alert color="red">{errorText(update.error)}</Alert> : null}
        {editing ? <EditSourceModal source={editing} onClose={() => setEditing(null)} /> : null}
      </Stack>
    </Card>
  );
}
