import {
  Accordion,
  Alert,
  Button,
  Card,
  Group,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import type { MatchList, MatchQuery } from "../app/apiClient";
import { WORK_MODE, label } from "../app/labels";
import { useMatches, useOverview } from "../app/queries";
import { JobDetailDrawer, JobMatchesTable } from "../components/JobMatchesTable";
import { PageFrame } from "../components/PageFrame";
import { EmptyState, type PageState } from "../components/states";

const SORT_OPTIONS = [
  { value: "ranking", label: "Paling cocok untukmu" },
  { value: "fit_score_desc", label: "Skor kecocokan tertinggi" },
  { value: "posted_at_desc", label: "Paling baru" },
];

const ELIGIBILITY_VIEWS = [
  { value: "all", label: "Semua" },
  { value: "eligible", label: "Sesuai syarat" },
  { value: "needs_review", label: "Perlu diperiksa" },
  { value: "ineligible", label: "Tidak sesuai" },
];

const WORK_MODE_OPTIONS = [
  { value: "", label: "Semua cara kerja" },
  { value: "remote", label: label(WORK_MODE, "remote") },
  { value: "onsite", label: label(WORK_MODE, "onsite") },
  { value: "hybrid", label: label(WORK_MODE, "hybrid") },
];

const FIT_OPTIONS = [
  { value: "0", label: "Semua skor" },
  { value: "55", label: "Cukup cocok (55+)" },
  { value: "75", label: "Cocok (75+)" },
  { value: "90", label: "Sangat cocok (90+)" },
];

type EligibilityFilter = NonNullable<MatchQuery["eligibility"]>;

/** Each eligibility filter pages independently; backend paginates per filter. */
type CursorPages = Record<EligibilityFilter, string[]>;

const EMPTY_PAGES: CursorPages = { all: [], eligible: [], needs_review: [], ineligible: [] };

function countFor(counts: MatchList["counts"] | undefined, value: string): string {
  if (!counts) return "";
  if (value === "all") return ` (${counts.eligible + counts.needs_review + counts.ineligible})`;
  return ` (${counts[value as "eligible" | "needs_review" | "ineligible"]})`;
}

export function MatchesPage() {
  const overview = useOverview();
  const [eligibility, setEligibility] = useState<EligibilityFilter>("all");
  const [sort, setSort] = useState<NonNullable<MatchQuery["sort"]>>("ranking");
  const [workMode, setWorkMode] = useState<string>("");
  const [minFit, setMinFit] = useState<string>("0");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState<CursorPages>(EMPTY_PAGES);
  const [selected, setSelected] = useState<string | null>(null);

  const ownPages = pages[eligibility];
  const cursor = ownPages.length > 0 ? ownPages[ownPages.length - 1] : null;
  const matches = useMatches({
    limit: 25,
    cursor,
    eligibility,
    sort,
    work_mode: workMode || undefined,
    min_fit_score: Number(minFit),
    q: query || undefined,
  });

  const loading = overview.isPending || matches.isPending;
  const failed = overview.isError || matches.isError;
  const items = matches.data?.items ?? [];
  const state: PageState = loading ? "loading" : failed ? "error" : "ready";
  const counts = matches.data?.counts;
  const total = counts ? counts.eligible + counts.needs_review + counts.ineligible : 0;
  const filtered = query !== "" || workMode !== "" || minFit !== "0";
  const profile = overview.data?.profile;
  const confirmed = profile?.status === "confirmed" && profile.active === true;

  function resetPaging() {
    setPages(EMPTY_PAGES);
  }

  function resetFilters() {
    setSearch("");
    setQuery("");
    setWorkMode("");
    setMinFit("0");
    setEligibility("all");
    setSort("ranking");
    resetPaging();
  }

  return (
    <PageFrame
      eyebrow="Langkah 3"
      title="Lowongan untukmu"
      description="Daftar lowongan yang sudah diperiksa syaratnya. Yang paling cocok muncul paling atas."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void matches.refetch();
      }}
      action={
        confirmed ? (
          <Button component={Link} to="/discovery" variant="light">
            Cari lowongan baru
          </Button>
        ) : null
      }
    >
      {!confirmed ? (
        <Alert color="orange" title="Selesaikan CV-mu dulu">
          <Stack gap="sm" align="flex-start">
            <Text size="sm">
              Daftar lowongan baru bisa dibuat setelah data CV-mu dikonfirmasi.
            </Text>
            <Button component={Link} to="/master-cv" variant="light">
              Buka CV Utama
            </Button>
          </Stack>
        </Alert>
      ) : (
        <Stack gap="lg">
          <Card withBorder>
            <Stack gap="md">
              <TextInput
                label="Cari lowongan"
                placeholder="Contoh: backend engineer, Jakarta, Acme"
                value={search}
                onChange={(event) => setSearch(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    setQuery(search.trim());
                    resetPaging();
                  }
                }}
              />

              <Group gap="xs" wrap="wrap">
                <SegmentedControl
                  value={eligibility}
                  onChange={(value) => {
                    setEligibility(value as EligibilityFilter);
                  }}
                  data={ELIGIBILITY_VIEWS.map((view) => ({
                    value: view.value,
                    label: `${view.label}${countFor(counts, view.value)}`,
                  }))}
                  size="sm"
                />
              </Group>

              <Accordion variant="contained">
                <Accordion.Item value="filter">
                  <Accordion.Control>
                    Filter lain{filtered ? " (sedang dipakai)" : ""}
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="sm">
                      <Select
                        label="Urutkan"
                        data={SORT_OPTIONS}
                        value={sort}
                        allowDeselect={false}
                        onChange={(value) => {
                          if (value) {
                            setSort(value as NonNullable<MatchQuery["sort"]>);
                            resetPaging();
                          }
                        }}
                      />
                      <Select
                        label="Cara kerja"
                        data={WORK_MODE_OPTIONS}
                        value={workMode}
                        allowDeselect={false}
                        onChange={(value) => {
                          setWorkMode(value ?? "");
                          resetPaging();
                        }}
                      />
                      <Select
                        label="Kecocokan minimum"
                        data={FIT_OPTIONS}
                        value={minFit}
                        allowDeselect={false}
                        onChange={(value) => {
                          setMinFit(value ?? "0");
                          resetPaging();
                        }}
                      />
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>

              <Group gap="xs">
                <Button
                  onClick={() => {
                    setQuery(search.trim());
                    resetPaging();
                  }}
                >
                  Cari
                </Button>
                <Button variant="subtle" onClick={resetFilters} disabled={!filtered && !search}>
                  Hapus semua filter
                </Button>
              </Group>

              {matches.data && matches.data.counts.hidden_by_min_fit_score > 0 ? (
                <Text size="sm" c="dimmed">
                  {matches.data.counts.hidden_by_min_fit_score} lowongan disembunyikan karena skor
                  kecocokannya di bawah batas yang kamu pilih.
                </Text>
              ) : null}
            </Stack>
          </Card>

          {state === "ready" && items.length === 0 ? (
            total === 0 ? (
              <EmptyState
                title="Belum ada lowongan"
                message="Jalankan pencarian lowongan dulu. Setelah itu daftar ini akan terisi sendiri."
                action={
                  <Button component={Link} to="/discovery">
                    Cari lowongan
                  </Button>
                }
              />
            ) : (
              <EmptyState
                title="Tidak ada yang cocok dengan filter ini"
                message="Coba hapus filter atau longgarkan batas kecocokan."
                action={<Button onClick={resetFilters}>Hapus filter</Button>}
              />
            )
          ) : null}

          {state === "ready" && items.length > 0 ? (
            <Card withBorder>
              <Stack gap="md">
                <Title order={3}>
                  {items.length} lowongan
                </Title>
                <JobMatchesTable items={items} onSelect={setSelected} />
                <Group justify="space-between">
                  <Button
                    variant="light"
                    disabled={ownPages.length === 0}
                    onClick={() => setPages({ ...pages, [eligibility]: ownPages.slice(0, -1) })}
                  >
                    Sebelumnya
                  </Button>
                  <Text size="sm" c="dimmed">Halaman {ownPages.length + 1}</Text>
                  <Button
                    variant="light"
                    disabled={!matches.data?.page.has_more}
                    onClick={() => {
                      const next = matches.data?.page.next_cursor;
                      if (next) setPages({ ...pages, [eligibility]: [...ownPages, next] });
                    }}
                  >
                    Berikutnya
                  </Button>
                </Group>
              </Stack>
            </Card>
          ) : null}

          {items.length > 0 ? (
            <Text size="sm" c="dimmed">
              Kecocokan dihitung dari isi CV Utama dan syarat tiap lowongan.
            </Text>
          ) : null}
        </Stack>
      )}

      <JobDetailDrawer jobId={selected} onClose={() => setSelected(null)} />
    </PageFrame>
  );
}
