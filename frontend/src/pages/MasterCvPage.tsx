import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";

import { ApiError, type ProfileSummary } from "../app/apiClient";
import {
  useConfirmProfile,
  useCorrectProfile,
  useMasterCv,
  useProfileVersion,
  useProfiles,
  useRollbackProfile,
  useStartExtraction,
  useUploadMasterCv,
} from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { ProfileReviewTable } from "../components/ProfileReviewTable";
import type { PageState } from "../components/states";

function statusColor(status: string): string {
  if (status === "confirmed") return "teal";
  if (status === "draft" || status === "in_review") return "yellow";
  if (status === "superseded") return "gray";
  return "blue";
}

function pickReviewTarget(items: ProfileSummary[] | undefined): string | null {
  if (!items || items.length === 0) return null;
  const active = items.find((item) => item.active);
  return (active ?? items[0]).profile_version_id;
}

export function MasterCvPage() {
  const masterCv = useMasterCv();
  const profiles = useProfiles();
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const upload = useUploadMasterCv();
  const extract = useStartExtraction();
  const correct = useCorrectProfile();
  const confirm = useConfirmProfile();
  const rollback = useRollbackProfile();

  const targetId = selected ?? pickReviewTarget(profiles.data?.items);
  const profile = useProfileVersion(targetId);

  const state: PageState = masterCv.isPending
    ? "loading"
    : masterCv.isError
      ? "error"
      : "ready";

  const error =
    (upload.error as ApiError | null) ??
    (extract.error as ApiError | null) ??
    (correct.error as ApiError | null) ??
    (confirm.error as ApiError | null) ??
    (rollback.error as ApiError | null);

  const confirmed = profiles.data?.items.find((item) => item.active && item.status === "confirmed");

  return (
    <PageFrame
      title="Master CV"
      description="Master CV immutable. Profil dan dokumen lamaran adalah turunan."
      state={state}
      onRetry={() => void masterCv.refetch()}
    >
      <Stack gap="md">
        {error ? (
          <Alert color="red" title="Aksi gagal">
            {error.message} ({error.code})
          </Alert>
        ) : null}
        {notice ? <Alert color="teal">{notice}</Alert> : null}

        <Card withBorder>
          <Stack gap="sm">
            <Title order={4}>Unggah</Title>
            <Text size="sm" c="dimmed">
              PDF teks, DOCX, TXT, atau MD. Maksimum 20 MB, PDF maksimum 50 halaman.
            </Text>
            <Group align="end">
              <FileInput
                label="File Master CV"
                placeholder="Pilih file"
                accept=".pdf,.docx,.txt,.md"
                value={file}
                onChange={setFile}
                flex={1}
              />
              <Button
                disabled={!file || upload.isPending}
                onClick={() => {
                  if (!file) return;
                  upload.mutate(file, {
                    onSuccess: (result) =>
                      setNotice(
                        result.deduplicated
                          ? "File identik sudah tersimpan. Tidak ada Master CV baru."
                          : "Master CV tersimpan.",
                      ),
                  });
                }}
              >
                Unggah
              </Button>
            </Group>
          </Stack>
        </Card>

        <Tabs defaultValue="original" keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="original">Original CV</Tabs.Tab>
            <Tabs.Tab value="profile">Verified Profile</Tabs.Tab>
            <Tabs.Tab value="history">History</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="original" pt="md">
            {masterCv.data ? (
              <Stack gap="sm">
                <Group>
                  <Badge variant="light" color={statusColor(masterCv.data.status)}>
                    {masterCv.data.status}
                  </Badge>
                  <Text size="sm">{masterCv.data.original_file.filename}</Text>
                  <Text size="sm" c="dimmed">
                    {(masterCv.data.original_file.size_bytes / 1024).toFixed(1)} KB
                    {masterCv.data.original_file.page_count
                      ? ` · ${masterCv.data.original_file.page_count} halaman`
                      : ""}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed" ff="monospace">
                  sha256 {masterCv.data.original_file.sha256}
                </Text>
                <Group>
                  <Button
                    component="a"
                    href="/api/setup/master-cv/file"
                    variant="light"
                    size="compact-sm"
                  >
                    Unduh file asli
                  </Button>
                  <Button
                    size="compact-sm"
                    disabled={extract.isPending}
                    onClick={() =>
                      extract.mutate(undefined, {
                        onSuccess: (task) =>
                          setNotice(
                            task.status === "completed"
                              ? "Ekstraksi selesai. Review profil di tab Verified Profile."
                              : `Task ekstraksi ${task.status}.`,
                          ),
                      })
                    }
                  >
                    Ekstrak profil
                  </Button>
                </Group>
                <Alert color="gray">
                  Mulai pencarian terkunci sampai profil dikonfirmasi.
                </Alert>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Belum ada Master CV. Unggah file untuk memulai.
              </Text>
            )}
          </Tabs.Panel>

          <Tabs.Panel value="profile" pt="md">
            {profile.data ? (
              <Stack gap="md">
                <Group justify="space-between">
                  <Group>
                    <Badge variant="light" color={statusColor(profile.data.status)}>
                      {profile.data.status}
                    </Badge>
                    <Text size="sm">
                      versi {profile.data.version} · {profile.data.profile_version_id}
                    </Text>
                  </Group>
                  <Group>
                    <Button
                      disabled={profile.data.conflicts.length > 0 || confirm.isPending}
                      onClick={() =>
                        confirm.mutate(
                          { profileVersionId: profile.data.profile_version_id },
                          {
                            onSuccess: () =>
                              setNotice("Profil dikonfirmasi. Discovery sekarang terbuka."),
                          },
                        )
                      }
                    >
                      Konfirmasi profil
                    </Button>
                  </Group>
                </Group>
                <Text size="sm" c="dimmed">
                  Setiap fakta menampilkan kutipan sumber dan status buktinya. Konfirmasi profil
                  bukan consent provider dan bukan approval dokumen.
                </Text>
                <ProfileReviewTable
                  profile={profile.data}
                  disabled={correct.isPending}
                  onCorrect={(path, value) =>
                    correct.mutateAsync({
                      profileVersionId: profile.data.profile_version_id,
                      expectedVersion: profile.data.version,
                      path,
                      value,
                    })
                  }
                  onResolveConflict={(conflictId, value) =>
                    correct.mutateAsync({
                      profileVersionId: profile.data.profile_version_id,
                      expectedVersion: profile.data.version,
                      path: `conflicts.${conflictId}`,
                      value,
                    })
                  }
                />
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Belum ada profil. Jalankan ekstraksi dari tab Original CV.
              </Text>
            )}
          </Tabs.Panel>

          <Tabs.Panel value="history" pt="md">
            {profiles.data && profiles.data.items.length > 0 ? (
              <Stack gap="sm">
                <Table withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Versi</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Dibuat</Table.Th>
                      <Table.Th>Aksi</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {profiles.data.items.map((item) => (
                      <Table.Tr key={item.profile_version_id}>
                        <Table.Td>
                          <Text size="sm">
                            v{item.version} · {item.profile_version_id}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="light" color={statusColor(item.status)}>
                            {item.status}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{item.created_at}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <Button
                              size="compact-xs"
                              variant="subtle"
                              onClick={() => setSelected(item.profile_version_id)}
                            >
                              Lihat
                            </Button>
                            <Button
                              size="compact-xs"
                              variant="light"
                              disabled={
                                item.active ||
                                !item.confirmed_at ||
                                rollback.isPending ||
                                !confirmed
                              }
                              onClick={() =>
                                rollback.mutate(
                                  {
                                    targetProfileVersionId: item.profile_version_id,
                                    reason: "rollback dari halaman Master CV",
                                  },
                                  { onSuccess: () => setNotice("Profil aktif dipindahkan.") },
                                )
                              }
                            >
                              Rollback
                            </Button>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                <Text size="sm" c="dimmed">
                  Rollback hanya memindahkan pointer aktif. Tidak menghapus versi dan tidak
                  mengubah isi.
                </Text>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Belum ada riwayat versi.
              </Text>
            )}
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </PageFrame>
  );
}
