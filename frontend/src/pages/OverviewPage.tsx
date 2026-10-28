import { Button, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { Link } from "react-router";

import { APPLICATION_STATUS, NEXT_ACTION, RUN_STATUS, WORKFLOW, label } from "../app/labels";
import { useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import { StatusBadge, type PageState } from "../components/states";

/** The three milestones a person passes in order. Each one is a real backend fact. */
const STEPS = [
  { key: "cv", label: "Simpan CV Utama", route: "/master-cv" },
  { key: "profile", label: "Periksa data CV", route: "/master-cv" },
  { key: "jobs", label: "Lowongan siap dilamar", route: "/matches" },
] as const;

export function OverviewPage() {
  const overview = useOverview();
  const state: PageState = overview.isPending
    ? "loading"
    : overview.isError
      ? "error"
      : overview.data
        ? "ready"
        : "empty";

  const data = overview.data;
  const next = data ? (NEXT_ACTION[data.next_action.code] ?? NEXT_ACTION.none) : NEXT_ACTION.none;
  const target = data?.next_action.target_route ?? "/master-cv";
  const confirmed = data?.profile?.status === "confirmed" && data.profile.active === true;
  const hasCv = Boolean(data?.master_cv);
  const done: Record<(typeof STEPS)[number]["key"], boolean> = {
    cv: hasCv,
    profile: confirmed,
    jobs: (data?.counts.eligible ?? 0) > 0,
  };
  const activeCount = data?.counts.eligible ?? 0;

  return (
    <PageFrame
      eyebrow="Beranda"
      title={hasCv ? "Selamat datang kembali" : "Selamat datang di Gawe"}
      description={
        hasCv
          ? "Semua pekerjaan lamaranmu ada di sini. Mulai dari langkah yang paling atas."
          : "Gawe membantu menyiapkan CV dan surat lamaran yang sesuai untuk setiap lowongan. Mulai dengan menyimpan CV-mu."
      }
      state={state}
      onRetry={() => void overview.refetch()}
    >
      {data ? (
        <Stack gap="lg">
          <Card withBorder bg="indigo.0">
            <Stack gap="sm">
              <Text size="xs" fw={600} tt="uppercase" c="indigo.7">
                Langkah berikutnya
              </Text>
              <Title order={2} fz={{ base: 22, md: 26 }}>
                {next.title}
              </Title>
              <Text c="dimmed" maw={620}>
                {next.hint}
              </Text>
              <Group mt={4}>
                <Button component={Link} to={target} size="md">
                  {next.title}
                </Button>
                {data.counts.documents_pending_review > 0 ? (
                  <Button component={Link} to="/applications" variant="light">
                    Lihat {data.counts.documents_pending_review} dokumen menunggu
                  </Button>
                ) : null}
              </Group>
            </Stack>
          </Card>

          {data.consent_required ? (
            <Card withBorder bg="orange.0">
              <Stack gap="sm" align="flex-start">
                <Text fw={600}>Izin pengiriman data</Text>
                <Text size="sm">
                  Gawe perlu mengirim sebagian isi CV-mu ke layanan AI untuk membaca dan menulis
                  draf dokumen. Tanpa izinmu, langkah itu tidak berjalan.
                </Text>
                <Button component={Link} to="/settings" variant="light" color="orange">
                  Atur izin sekarang
                </Button>
              </Stack>
            </Card>
          ) : null}

          <div>
            <Title order={4} mb="sm">
              Progres kamu
            </Title>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
              {STEPS.map((step, index) => (
                <Card key={step.key} withBorder padding="md">
                  <Group gap="sm" wrap="nowrap" align="flex-start">
                    <ThemeIcon
                      size={28}
                      radius="xl"
                      variant={done[step.key] ? "filled" : "light"}
                      color={done[step.key] ? "teal" : "gray"}
                      aria-label={done[step.key] ? "sudah" : "belum"}
                    >
                      <Text size="xs" fw={700}>
                        {index + 1}
                      </Text>
                    </ThemeIcon>
                    <div>
                      <Text size="sm" fw={600}>
                        {step.label}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {done[step.key] ? "Sudah selesai" : "Belum selesai"}
                      </Text>
                    </div>
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
          </div>

          <Card withBorder>
            <Stack gap="sm">
              <Title order={4}>Lowongan untukmu</Title>
              {activeCount > 0 ? (
                <Text>
                  Ada <strong>{activeCount} lowongan</strong> yang sesuai dengan syaratmu dan siap
                  dibuatkan CV.
                </Text>
              ) : (
                <Text c="dimmed">
                  Belum ada lowongan yang siap dilamar. Jalankan pencarian setelah data CV-mu
                  dikonfirmasi.
                </Text>
              )}
              <Group>
                <Button component={Link} to="/matches" variant="light">
                  Lihat lowongan
                </Button>
                <Button component={Link} to="/applications" variant="subtle">
                  Lamaran saya
                </Button>
              </Group>
            </Stack>
          </Card>

          {data.recent_activity.length > 0 ? (
            <Card withBorder>
              <Stack gap="sm">
                <Title order={4}>Aktivitas terakhir</Title>
                <Stack gap="xs">
                  {data.recent_activity.map((event) => (
                    <Group key={event.event_id} justify="space-between" wrap="nowrap" gap="md">
                      <Stack gap={0}>
                        <Text size="sm">{event.summary}</Text>
                        <Text size="xs" c="dimmed">
                          {label(WORKFLOW, event.workflow)} · {event.occurred_at}
                        </Text>
                      </Stack>
                      <StatusBadge
                        status={event.status_context.value}
                        label={label(
                          event.workflow === "discovery" ? RUN_STATUS : APPLICATION_STATUS,
                          event.status_context.value,
                        )}
                      />
                    </Group>
                  ))}
                </Stack>
              </Stack>
            </Card>
          ) : null}
        </Stack>
      ) : null}
    </PageFrame>
  );
}

