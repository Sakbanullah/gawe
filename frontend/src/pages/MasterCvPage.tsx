import {
  Alert,
  Badge,
  Button,
  Card,
  FileInput,
  Group,
  List,
  Stack,
  Table,
  Tabs,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { useState } from "react";

import { friendlyError } from "../app/errors";
import { PROFILE_STATUS, label } from "../app/labels";
import type { ProfileSummary } from "../app/apiClient";
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
import { EmptyState, type PageState } from "../components/states";

/** Newest unfinished version first, so the review target is obvious. */
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

  const state: PageState = masterCv.isPending ? "loading" : masterCv.isError ? "error" : "ready";

  const error =
    upload.error ?? extract.error ?? correct.error ?? confirm.error ?? rollback.error ?? null;
  const confirmed = profiles.data?.items.find((item) => item.active && item.status === "confirmed");
  const hasFile = Boolean(masterCv.data);
  const profileReady = Boolean(profile.data);

  return (
    <PageFrame
      eyebrow="Langkah 1"
      title="CV Utama"
      description="Simpan CV yang biasa kamu kirim. Gawe membaca isinya sekali, lalu memakainya untuk menyiapkan CV yang sesuai tiap lowongan. File aslinya tidak diubah."
      state={state}
      onRetry={() => void masterCv.refetch()}
    >
      <Stack gap="lg">
        {error ? (
          <Alert color="red" title="Belum berhasil">
            {friendlyError(error)}
          </Alert>
        ) : null}
        {notice ? (
          <Alert color="teal" title="Tersimpan">
            {notice}
          </Alert>
        ) : null}

        {!hasFile ? (
          <Card withBorder>
            <Stack gap="sm">
              <Title order={3}>Simpan CV-mu</Title>
              <Text c="dimmed">
                Pilih file CV dalam format PDF, DOCX, TXT, atau MD. Ukuran maksimal 20 MB.
              </Text>
              <FileInput
                label="File CV"
                description="Pilih dari komputer ini."
                placeholder="Pilih file CV"
                accept=".pdf,.docx,.txt,.md"
                value={file}
                onChange={setFile}
                leftSection={null}
              />
              <Group>
                <Button
                  size="md"
                  disabled={!file || upload.isPending}
                  loading={upload.isPending}
                  onClick={() => {
                    if (!file) return;
                    upload.mutate(file, {
                      onSuccess: (result) =>
                        setNotice(
                          result.deduplicated
                            ? "File ini sudah pernah kamu simpan. Tidak ada yang berubah."
                            : "CV-mu tersimpan. Langkah berikutnya: baca isinya.",
                        ),
                    });
                  }}
                >
                  Simpan CV
                </Button>
              </Group>
              <Text size="sm" c="dimmed">
                File hanya tersimpan di komputer ini.
              </Text>
            </Stack>
          </Card>
        ) : null}

        <Tabs defaultValue={hasFile ? "profile" : "file"} keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="file">File CV</Tabs.Tab>
            <Tabs.Tab value="profile">Data CV-mu</Tabs.Tab>
            <Tabs.Tab value="history">Riwayat</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="file" pt="md">
            {masterCv.data ? (
              <Card withBorder>
                <Stack gap="md">
                  <Group justify="space-between" wrap="wrap" gap="sm">
                    <div>
                      <Text fw={600}>{masterCv.data.original_file.filename}</Text>
                      <Text size="sm" c="dimmed">
                        {(masterCv.data.original_file.size_bytes / 1024).toFixed(0)} KB
                        {masterCv.data.original_file.page_count
                          ? ` · ${masterCv.data.original_file.page_count} halaman`
                          : ""}
                      </Text>
                    </div>
                    <Badge color={confirmed ? "teal" : "gray"} variant="light">
                      {confirmed ? "Sudah dipakai" : "Tersimpan"}
                    </Badge>
                  </Group>

                  <Group>
                    <Button
                      loading={extract.isPending}
                      disabled={extract.isPending}
                      onClick={() =>
                        extract.mutate(undefined, {
                          onSuccess: (task) =>
                            setNotice(
                              task.status === "completed"
                                ? "Selesai membaca CV. Sekarang periksa data di tab Data CV-mu."
                                : "Gawe masih membaca CV-mu. Hasilnya muncul di tab Data CV-mu.",
                            ),
                        })
                      }
                    >
                      {profileReady ? "Baca ulang isi CV" : "Baca isi CV-mu"}
                    </Button>
                    <Button
                      component="a"
                      href="/api/setup/master-cv/file"
                      variant="light"
                      download
                    >
                      Unduh file asli
                    </Button>
                  </Group>

                  <List
                    spacing={6}
                    size="sm"
                    icon={
                      <ThemeIcon color="gray" size={18} radius="xl" variant="light">
                        <Text size="xs">•</Text>
                      </ThemeIcon>
                    }
                  >
                    <List.Item>Gawe tidak mengubah file CV asli.</List.Item>
                    <List.Item>
                      Pencarian lowongan terbuka setelah data CV-mu kamu konfirmasi.
                    </List.Item>
                  </List>

                  {file ? (
                    <Group align="flex-end" gap="sm">
                      <FileInput
                        label="Ganti dengan file lain"
                        placeholder="Pilih file baru"
                        accept=".pdf,.docx,.txt,.md"
                        value={file}
                        onChange={setFile}
                        style={{ flex: 1 }}
                      />
                      <Button
                        variant="light"
                        loading={upload.isPending}
                        disabled={!file}
                        onClick={() => {
                          if (!file) return;
                          upload.mutate(file, {
                            onSuccess: () => setNotice("File CV diganti. Baca ulang isinya."),
                          });
                        }}
                      >
                        Simpan file baru
                      </Button>
                    </Group>
                  ) : null}
                </Stack>
              </Card>
            ) : (
              <EmptyState message="Belum ada file CV tersimpan. Pilih file di atas untuk memulai." />
            )}
          </Tabs.Panel>

          <Tabs.Panel value="profile" pt="md">
            {profile.data ? (
              <Stack gap="md">
                <Card withBorder>
                  <Group justify="space-between" wrap="wrap" gap="sm">
                    <div>
                      <Group gap="xs">
                        <Text fw={600}>Versi {profile.data.version}</Text>
                        <Badge
                          color={profile.data.status === "confirmed" ? "teal" : "orange"}
                          variant="light"
                        >
                          {label(PROFILE_STATUS, profile.data.status)}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed" mt={4}>
                        Periksa setiap baris. Kalau ada yang salah, tekan Ubah. Kalau sudah benar
                        semua, tekan tombol konfirmasi.
                      </Text>
                    </div>
                    <Button
                      disabled={profile.data.conflicts.length > 0 || confirm.isPending}
                      loading={confirm.isPending}
                      onClick={() =>
                        confirm.mutate(
                          { profileVersionId: profile.data.profile_version_id },
                          {
                            onSuccess: () =>
                              setNotice(
                                "Data CV-mu sudah dikonfirmasi. Sekarang Gawe bisa mencari lowongan.",
                              ),
                          },
                        )
                      }
                    >
                      Data ini sudah benar
                    </Button>
                  </Group>
                  {profile.data.conflicts.length > 0 ? (
                    <Alert color="orange" mt="md" title="Ada data yang berbeda">
                      Gawe menemukan dua versi data yang berbeda. Pilih yang benar di bawah sebelum
                      konfirmasi.
                    </Alert>
                  ) : null}
                </Card>
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
              <EmptyState
                title="CV belum dibaca"
                message="Buka tab File CV, lalu tekan Baca isi CV-mu. Setelah itu datanya muncul di sini."
              />
            )}
          </Tabs.Panel>

          <Tabs.Panel value="history" pt="md">
            {profiles.data && profiles.data.items.length > 0 ? (
              <Card withBorder>
                <Stack gap="sm">
                  <Text size="sm" c="dimmed">
                    Setiap kali kamu memperbaiki data, Gawe menyimpan versi baru. Versi lama tetap
                    ada, jadi kamu bisa kembali kapan saja.
                  </Text>
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Versi</Table.Th>
                        <Table.Th>Status</Table.Th>
                        <Table.Th>Dibuat</Table.Th>
                        <Table.Th>Yang dipakai</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {profiles.data.items.map((item) => (
                        <Table.Tr key={item.profile_version_id}>
                          <Table.Td>Versi {item.version}</Table.Td>
                          <Table.Td>{label(PROFILE_STATUS, item.status)}</Table.Td>
                          <Table.Td>{item.created_at}</Table.Td>
                          <Table.Td>
                            <Group gap="xs">
                              <Button
                                size="compact-sm"
                                variant="subtle"
                                onClick={() => setSelected(item.profile_version_id)}
                              >
                                Lihat
                              </Button>
                              <Button
                                size="compact-sm"
                                variant="light"
                                disabled={
                                  item.active || !item.confirmed_at || rollback.isPending || !confirmed
                                }
                                onClick={() =>
                                  rollback.mutate(
                                    {
                                      targetProfileVersionId: item.profile_version_id,
                                      reason: "rollback dari halaman Master CV",
                                    },
                                    { onSuccess: () => setNotice("Versi yang dipakai sudah diganti.") },
                                  )
                                }
                              >
                                Pakai versi ini
                              </Button>
                            </Group>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                  <Text size="sm" c="dimmed">
                    Memakai versi lama tidak menghapus versi lain.
                  </Text>
                </Stack>
              </Card>
            ) : (
              <EmptyState message="Belum ada riwayat. Riwayat muncul setelah CV-mu dibaca pertama kali." />
            )}
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </PageFrame>
  );
}
