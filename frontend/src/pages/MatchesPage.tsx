import { Table, Text } from "@mantine/core";

import { useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import type { PageState } from "../components/states";

export function MatchesPage() {
  const overview = useOverview();
  const state: PageState = overview.isPending ? "loading" : overview.isError ? "error" : "empty";

  return (
    <PageFrame
      title="Job Matches"
      description="Eligibility, fit, dan prioritas ditampilkan terpisah. Urutan berasal dari backend."
      state={state}
      onRetry={() => void overview.refetch()}
    >
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Judul</Table.Th>
            <Table.Th>Perusahaan</Table.Th>
            <Table.Th>Eligibility</Table.Th>
            <Table.Th>Fit</Table.Th>
            <Table.Th>Prioritas</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td colSpan={5}>
              <Text c="dimmed">Belum ada job match.</Text>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </PageFrame>
  );
}
