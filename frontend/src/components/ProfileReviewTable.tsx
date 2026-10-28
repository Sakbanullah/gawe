import { Alert, Badge, Button, Card, Group, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useState } from "react";

import { collectionLabel, fieldLabel } from "../app/labels";
import type { ProfileVersion } from "../app/apiClient";

type Fact = {
  path: string;
  section: string;
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
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(text).join(", ");
  return String(value);
}

function refs(item: Record<string, unknown>): string[] {
  const list = item.evidence;
  return Array.isArray(list) ? list.filter((ref): ref is string => typeof ref === "string") : [];
}

/** One readable row per fact. Internal ids stay in the path, never in the text. */
function facts(content: ProfileContent): Fact[] {
  const rows: Fact[] = [];
  const personal = content.personal ?? {};
  for (const field of ["full_name", "email", "phone", "location", "links"]) {
    rows.push({
      path: `personal.${field}`,
      section: "Data diri",
      label: fieldLabel(field),
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
    const section = collectionLabel(key);
    for (const item of content[key] ?? []) {
      const id = text(item.id);
      const heading = text(item.title ?? item.name ?? item.degree ?? item.institution ?? "");
      rows.push({
        path: `${key}.${id}`,
        section,
        label: heading === "—" ? section : heading,
        value: Object.entries(item)
          .filter(
            ([name]) =>
              !["id", "evidence", "bullets", "title", "name", "degree", "institution"].includes(
                name,
              ),
          )
          .map(([name, value]) => `${fieldLabel(name)}: ${text(value)}`)
          .join(" · "),
        evidence: refs(item),
        evidenceRequired: true,
      });
      for (const bullet of (item.bullets as Record<string, unknown>[] | undefined) ?? []) {
        rows.push({
          path: `${key}.${id}.bullets.${text(bullet.id)}`,
          section,
          label: "Poin pencapaian",
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
    section: "Preferensi kerja",
    label: "Preferensi kerja",
    value: Object.entries(preferences)
      .map(([name, value]) => `${fieldLabel(name)}: ${text(value)}`)
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
    return { label: "Tanpa kutipan", color: "gray", quote: "", locator: "" };
  }
  const declared = entries.every((entry) => entry.source === "user_declaration");
  const locator = entries
    .map((entry) => {
      const parts = entry.locator ?? {};
      const page = parts.page ? `halaman ${parts.page}` : null;
      return [page, parts.section ?? null].filter(Boolean).join(" ");
    })
    .filter(Boolean)
    .join(", ");
  return {
    label: declared ? "Dari kamu" : "Dari CV",
    color: declared ? "indigo" : "teal",
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
  const sections = [...new Set(rows.map((row) => row.section))];

  async function save(path: string) {
    await onCorrect(path, draft);
    setEditing(null);
    setDraft("");
  }

  return (
    <Stack gap="lg">
      {profile.conflicts.length > 0 ? (
        <Alert color="yellow" title="Ada data yang berbeda">
          CV-mu menyebut dua hal berbeda di bagian ini. Pilih yang benar supaya Gawe tidak menebak.
        </Alert>
      ) : null}

      {sections.map((section) => (
        <Card key={section} withBorder>
          <Stack gap="sm">
            <Title order={3}>{section}</Title>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w="26%">Bagian</Table.Th>
                  <Table.Th>Isi</Table.Th>
                  <Table.Th w="18%">Sumber</Table.Th>
                  <Table.Th w="12%" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows
                  .filter((row) => row.section === section)
                  .map((row) => {
                    const status = row.evidenceRequired
                      ? evidenceStatus(row.evidence, profile.evidence_index)
                      : { label: "—", color: "gray", quote: "", locator: "" };
                    const isEditing = editing === row.path;
                    return (
                      <Table.Tr key={row.path}>
                        <Table.Td>
                          <Text size="sm" fw={500}>
                            {row.label}
                          </Text>
                          {status.quote || status.locator ? (
                            <Text size="xs" c="dimmed" mt={2}>
                              {[status.quote, status.locator].filter(Boolean).join(" · ")}
                            </Text>
                          ) : null}
                        </Table.Td>
                        <Table.Td>
                          {isEditing ? (
                            <TextInput
                              aria-label={`Ubah ${row.label}`}
                              value={draft}
                              onChange={(event) => setDraft(event.currentTarget.value)}
                              autoFocus
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
                          {isEditing ? (
                            <Group gap={4} wrap="nowrap">
                              <Button size="compact-sm" onClick={() => void save(row.path)}>
                                Simpan
                              </Button>
                              <Button
                                size="compact-sm"
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
                              size="compact-sm"
                              variant="light"
                              disabled={disabled}
                              onClick={() => {
                                setEditing(row.path);
                                setDraft(row.value === "—" ? "" : row.value);
                              }}
                            >
                              Ubah
                            </Button>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
              </Table.Tbody>
            </Table>
          </Stack>
        </Card>
      ))}

      {profile.conflicts.length > 0 ? (
        <Card withBorder>
          <Stack gap="sm">
            <Title order={3}>Pilih yang benar</Title>
            {profile.conflicts.map((conflict: Conflict) => (
              <Alert key={conflict.conflict_id} color="yellow" title={collectionLabel(conflict.path.split(".")[0])}>
                <Stack gap="xs">
                  {conflict.candidates.map((candidate, index) => (
                    <Group key={index} justify="space-between">
                      <Text size="sm">{text(candidate.value)}</Text>
                      <Button
                        size="compact-sm"
                        variant="light"
                        disabled={disabled}
                        onClick={() => void onResolveConflict(conflict.conflict_id, candidate.value)}
                      >
                        Pakai ini
                      </Button>
                    </Group>
                  ))}
                </Stack>
              </Alert>
            ))}
          </Stack>
        </Card>
      ) : null}
    </Stack>
  );
}
