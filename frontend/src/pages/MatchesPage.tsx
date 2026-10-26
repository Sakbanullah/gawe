import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router";

import type { MatchList, MatchQuery } from "../app/apiClient";
import { useMatches, useOverview } from "../app/queries";
import { JobDetailDrawer, JobMatchesTable } from "../components/JobMatchesTable";
import { PageFrame } from "../components/PageFrame";
import type { PageState } from "../components/states";

const SORT_LABEL: Record<NonNullable<MatchQuery["sort"]>, string> = {
  ranking: "Ranking backend (default)",
  fit_score_desc: "Fit tertinggi (tampilan)",
  posted_at_desc: "Terbaru (tampilan)",
  priority_tier: "Priority tier (tampilan)",
};

const ELIGIBILITY_OPTIONS = [
  { value: "all", label: "Semua" },
  { value: "eligible", label: "Eligible" },
  { value: "needs_review", label: "Needs review" },
  { value: "ineligible", label: "Ineligible" },
];

const STATUS_ORDER = ["eligible", "needs_review", "ineligible"] as const;

type EligibilityFilter = NonNullable<MatchQuery["eligibility"]>;

/** Each eligibility filter pages independently; backend paginates per filter. */
type CursorPages = Record<EligibilityFilter, string[]>;

const EMPTY_PAGES: CursorPages = { all: [], eligible: [], needs_review: [], ineligible: [] };

const GROUP_LABEL: Record<(typeof STATUS_ORDER)[number], string> = {
  eligible: "Eligible · ranked",
  needs_review: "Needs review · tanpa fit score",
  ineligible: "Ineligible · tanpa dokumen",
};

const TIER_OPTIONS = [
  { value: "", label: "Semua tier" },
  { value: "P1", label: "P1 · Global onsite" },
  { value: "P2", label: "P2 · Global remote" },
  { value: "P3", label: "P3 · Indonesia remote" },
  { value: "P4", label: "P4 · Indonesia onsite" },
  { value: "unclassified", label: "Belum terklasifikasi" },
];

const WORK_MODE_OPTIONS = [
  { value: "", label: "Semua mode" },
  { value: "onsite", label: "Onsite" },
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "unknown", label: "Tidak diketahui" },
];

const MARKET_OPTIONS = [
  { value: "", label: "Semua pasar" },
  { value: "indonesia", label: "Indonesia" },
  { value: "global", label: "Global" },
  { value: "unknown", label: "Tidak diketahui" },
];

const FIT_OPTIONS = [
  { value: "0", label: "Semua skor" },
  { value: "55", label: "≥ 55" },
  { value: "75", label: "≥ 75" },
  { value: "90", label: "≥ 90" },
];

function countFor(counts: MatchList["counts"] | undefined, value: string): string {
  if (!counts) return "";
  if (value === "all") {
    return ` (${counts.eligible + counts.needs_review + counts.ineligible})`;
  }
  const total = counts[value as "eligible" | "needs_review" | "ineligible"];
  return ` (${total})`;
}

export function MatchesPage() {
  const overview = useOverview();
  const [eligibility, setEligibility] = useState<NonNullable<MatchQuery["eligibility"]>>("all");
  const [sort, setSort] = useState<NonNullable<MatchQuery["sort"]>>("ranking");
  const [tier, setTier] = useState<string>("");
  const [workMode, setWorkMode] = useState<string>("");
  const [market, setMarket] = useState<string>("");
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
    tier: tier || undefined,
    work_mode: workMode || undefined,
    market: market || undefined,
    min_fit_score: Number(minFit),
    q: query || undefined,
  });

  const loading = overview.isPending || matches.isPending;
  const failed = overview.isError || matches.isError;
  const items = matches.data?.items ?? [];
  // Empty results keep the filters visible, so the page handles the empty case.
  const state: PageState = loading ? "loading" : failed ? "error" : "ready";
  // Contract: needs_review and ineligible are shown apart from the ranked list.
  const groups = STATUS_ORDER.map((status) => ({
    status,
    rows: items.filter((item) => item.eligibility.status === status),
  })).filter((group) => group.rows.length > 0);

  const profile = overview.data?.profile;
  const confirmed = profile?.status === "confirmed" && profile.active === true;

  function resetPaging() {
    setPages(EMPTY_PAGES);
  }

  return (
    <PageFrame
      title="Job Matches"
      description="Eligibility, fit, dan prioritas ditampilkan terpisah. Urutan berasal dari backend."
      state={state}
      onRetry={() => {
        void overview.refetch();
        void matches.refetch();
      }}
    >
      {!confirmed ? (
        <Alert color="orange" title="Matches terkunci">
          <Stack gap="xs">
            <Text>Job Matches hanya tersedia setelah profil dikonfirmasi.</Text>
            <Group>
              <Button component={Link} to="/master-cv" variant="light">
                Buka Master CV
              </Button>
            </Group>
          </Stack>
        </Alert>
      ) : (
        <Stack gap="md">
          <Card withBorder>
            <Stack gap="sm">
              <Group gap="xs">
                {ELIGIBILITY_OPTIONS.map((option) => (
                  <Badge
                    key={option.value}
                    variant={eligibility === option.value ? "filled" : "light"}
                    color={
                      option.value === "eligible"
                        ? "green"
                        : option.value === "needs_review"
                          ? "yellow"
                          : option.value === "ineligible"
                            ? "red"
                            : "gray"
                    }
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      setEligibility(option.value as NonNullable<MatchQuery["eligibility"]>);
                    }}
                  >
                    {option.label}
                    {countFor(matches.data?.counts, option.value)}
                  </Badge>
                ))}
              </Group>

              <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
                <TextInput
                  label="Cari"
                  placeholder="Judul, perusahaan, lokasi"
                  value={search}
                  onChange={(event) => setSearch(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      setQuery(search.trim());
                      resetPaging();
                    }
                  }}
                />
                <Select
                  label="Urutan"
                  data={Object.entries(SORT_LABEL).map(([value, label]) => ({ value, label }))}
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
                  label="Tier"
                  data={TIER_OPTIONS}
                  value={tier}
                  allowDeselect={false}
                  onChange={(value) => {
                    setTier(value ?? "");
                    resetPaging();
                  }}
                />
                <Select
                  label="Mode kerja"
                  data={WORK_MODE_OPTIONS}
                  value={workMode}
                  allowDeselect={false}
                  onChange={(value) => {
                    setWorkMode(value ?? "");
                    resetPaging();
                  }}
                />
                <Select
                  label="Pasar"
                  data={MARKET_OPTIONS}
                  value={market}
                  allowDeselect={false}
                  onChange={(value) => {
                    setMarket(value ?? "");
                    resetPaging();
                  }}
                />
                <Select
                  label="Skor fit minimum"
                  data={FIT_OPTIONS}
                  value={minFit}
                  allowDeselect={false}
                  onChange={(value) => {
                    setMinFit(value ?? "0");
                    resetPaging();
                  }}
                />
              </SimpleGrid>

              <Group justify="space-between">
                <Group gap="xs">
                  <Button
                    variant="light"
                    onClick={() => {
                      setQuery(search.trim());
                      resetPaging();
                    }}
                  >
                    Terapkan pencarian
                  </Button>
                  <Button
                    variant="subtle"
                    onClick={() => {
                      setSearch("");
                      setQuery("");
                      setTier("");
                      setWorkMode("");
                      setMarket("");
                      setMinFit("0");
                      setEligibility("all");
                      setSort("ranking");
                      resetPaging();
                    }}
                  >
                    Reset filter
                  </Button>
                </Group>
                {sort !== "ranking" ? (
                  <Text size="sm" c="dimmed">
                    Urutan tampilan: {SORT_LABEL[sort]}. Ranking backend tetap tersimpan.
                  </Text>
                ) : null}
              </Group>

              {matches.data ? (
                <Text size="sm" c="dimmed">
                  {matches.data.counts.hidden_by_min_fit_score > 0
                    ? `${matches.data.counts.hidden_by_min_fit_score} lowongan tersembunyi oleh filter skor. `
                    : ""}
                  Ranking run: {matches.data.ranking.ranking_run_id ?? "belum ada"} · tie_window{" "}
                  {matches.data.ranking.tie_window} · tie-breaker{" "}
                  {matches.data.ranking.tie_breaker.join(" → ")}
                </Text>
              ) : null}
            </Stack>
          </Card>

          {state === "ready" && items.length === 0 ? (
            <Alert color="gray" title="Belum ada job match">
              Jalankan discovery dan pastikan profil sudah dikonfirmasi. Filter yang terlalu ketat
              juga dapat mengosongkan daftar.
            </Alert>
          ) : null}

          {state === "ready" && items.length > 0
            ? groups.map((group) => (
                <Stack key={group.status} gap="xs">
                  <Title order={4}>{GROUP_LABEL[group.status]}</Title>
                  <JobMatchesTable items={group.rows} onSelect={setSelected} />
                </Stack>
              ))
            : null}

          <Group justify="space-between">
            <Button
              variant="light"
              disabled={ownPages.length === 0}
              onClick={() => setPages({ ...pages, [eligibility]: ownPages.slice(0, -1) })}
            >
              Sebelumnya
            </Button>
            <Text size="sm" c="dimmed">
              Halaman {ownPages.length + 1} ·{" "}
              {ELIGIBILITY_OPTIONS.find((option) => option.value === eligibility)?.label ??
                "Semua"}
            </Text>
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
      )}

      <JobDetailDrawer jobId={selected} onClose={() => setSelected(null)} />
    </PageFrame>
  );
}
