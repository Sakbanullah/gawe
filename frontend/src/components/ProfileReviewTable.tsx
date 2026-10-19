import {
  Alert,
  Badge,
  Button,
  Group,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";

import type { ProfileVersion } from "../app/apiClient";

type Fact = {
  path: string;
  label: string;
  value: string;
  evidence: string[];
  evidenceRequired: boolean;
};

type Conflict = ProfileVersion["conflicts"][number];

type ProfileContent = {
  personal?: Record<string, unknown>;
  education?: Record<string, unknown>[];
  experience?: Record<string, unknown>[];
  skills?: Record<string, unknown>[];
  projects?: Record<string, unknown>[];
  certifications?: Record<string, unknown>[];
  languages?: Record<string, unknown>[];
  awards?: Record<string, unknown>[];
  work_authorization?: Record<string, unknown>[];
  work_preferences?: Record<string, unknown>;
};

function text(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (Array.isArray(value)) {
    return value.map(text).join(", ");
  }
  return String(value);
}

function refs(item: Record<string, unknown>): string[] {
  const list = item.evidence;
  return Array.isArray(list) ? list.filter((ref): ref is string => typeof ref === "string") : [];
}

function facts(content: ProfileContent): Fact[] {
  const rows: Fact[] = [];
  const personal = content.personal ?? {};
  for (const field of ["full_name", "email", "phone", "location", "links"]) {
    rows.push({
      path: `personal.${field}`,
      label: `personal.${field}`,
      value: text(personal[field]),
      // profile.schema.json has no evidence array on `personal`; the contract
      // only requires evidence on the fact collections below.
      evidence: [],
      evidenceRequired: false,
    });
  }
  for (const key of [
    "education",
    "experience",
    "skills",
    "projects",
    "certifications",
    "languages",
    "awards",
    "work_authorization",
  ] as const) {
    for (const item of content[key] ?? []) {
      const id = text(item.id);
      rows.push({
        path: `${key}.${id}`,
        label: `${key}.${id}`,
        value: Object.entries(item)
          .filter(([name]) => !["id", "evidence", "bullets"].includes(name))
          .map(([name, value]) => `${name}: ${text(value)}`)
          .join(" · "),
        evidence: refs(item),
        evidenceRequired: true,
      });
      for (const bullet of (item.bullets as Record<string, unknown>[] | undefined) ?? []) {
        rows.push({
          path: `${key}.${id}.bullets.${text(bullet.id)}`,
          label: `${key}.${id}.bullets.${text(bullet.id)}`,
          value: text(bullet.text),
          evidence: refs(bullet),
          evidenceRequired: true,
        });
      }
    }
  }
  const preferences = content.work_preferences ?? {};
  rows.push({
    path: "work_preferences",
    label: "work_preferences",
    value: Object.entries(preferences)
      .map(([name, value]) => `${name}: ${text(value)}`)
      .join(" · "),
    evidence: [],
    evidenceRequired: false,
  });
  return rows;
}

function evidenceStatus(
  evidence: string[],
  index: ProfileVersion["evidence_index"],
): { label: string; color: string; quote: string; locator: string } {
  const entries = evidence.map((ref) => index[ref]).filter(Boolean);
  if (entries.length === 0) {
    return { label: "tanpa bukti", color: "gray", quote: "", locator: "" };
  }
  const declared = entries.every((entry) => entry.source === "user_declaration");
  const locator = entries
    .map((entry) => {
      const parts = entry.locator ?? {};
      return [parts.page ? `p${parts.page}` : null, parts.block_id ?? parts.section]
        .filter(Boolean)
        .join(" ");
    })
    .filter(Boolean)
    .join(", ");
  return {
    label: declared ? "deklarasi pengguna" : "bukti CV",
    color: declared ? "blue" : "teal",
    quote: entries.map((entry) => entry.quote).join(" / "),
    locator,
  };
}

type Props = {
  profile: ProfileVersion;
  disabled?: boolean;
  onCorrect: (path: string, value: unknown) => Promise<unknown> | void;
  onResolveConflict: (conflictId: string, value: unknown) => Promise<unknown> | void;
};

export function ProfileReviewTable({ profile, disabled, onCorrect, onResolveConflict }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const rows = facts(profile.content as ProfileContent);

  async function save(path: string) {
    await onCorrect(path, draft);
    setEditing(null);
    setDraft("");
  }

  return (
    <Stack gap="md">
      {profile.conflicts.length > 0 ? (
        <Alert color="yellow" title="Konflik belum diselesaikan">
          Pilih nilai yang benar. Konflik tidak ditimpa otomatis dan memblokir konfirmasi.
        </Alert>
      ) : null}

      <Table withTableBorder highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Field</Table.Th>
            <Table.Th>Nilai</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Bukti</Table.Th>
            <Table.Th>Aksi</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => {
            const status = row.evidenceRequired
              ? evidenceStatus(row.evidence, profile.evidence_index)
              : { label: "—", color: "gray", quote: "", locator: "" };
            const isEditing = editing === row.path;
            return (
              <Table.Tr key={row.path}>
                <Table.Td>
                  <Text size="sm" ff="monospace">
                    {row.label}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {isEditing ? (
                    <TextInput
                      aria-label={`Koreksi ${row.label}`}
                      value={draft}
                      onChange={(event) => setDraft(event.currentTarget.value)}
                    />
                  ) : (
                    <Text size="sm">{row.value}</Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" color={status.color}>
                    {status.label}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Stack gap={2}>
                    <Text size="xs">{status.quote || "Tidak ada kutipan sumber."}</Text>
                    {status.locator ? (
                      <Text size="xs" c="dimmed">
                        {status.locator}
                      </Text>
                    ) : null}
                  </Stack>
                </Table.Td>
                <Table.Td>
                  {isEditing ? (
                    <Group gap="xs">
                      <Button size="compact-xs" onClick={() => void save(row.path)}>
                        Simpan
                      </Button>
                      <Button
                        size="compact-xs"
                        variant="subtle"
                        onClick={() => {
                          setEditing(null);
                          setDraft("");
                        }}
                      >
                        Batal
                      </Button>
                    </Group>
                  ) : (
                    <Button
                      size="compact-xs"
                      variant="light"
                      disabled={disabled}
                      onClick={() => {
                        setEditing(row.path);
                        setDraft(row.value === "—" ? "" : row.value);
                      }}
                    >
                      Edit
                    </Button>
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>

      {profile.conflicts.length > 0 ? (
        <Stack gap="xs">
          <Title order={5}>Konflik</Title>
          {profile.conflicts.map((conflict: Conflict) => (
            <Alert key={conflict.conflict_id} color="yellow" title={conflict.path}>
              <Stack gap="xs">
                {conflict.candidates.map((candidate, index) => (
                  <Group key={index} justify="space-between">
                    <Text size="sm">{text(candidate.value)}</Text>
                    <Button
                      size="compact-xs"
                      variant="light"
                      disabled={disabled}
                      onClick={() =>
                        void onResolveConflict(conflict.conflict_id, candidate.value)
                      }
                    >
                      Gunakan nilai ini
                    </Button>
                  </Group>
                ))}
              </Stack>
            </Alert>
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
