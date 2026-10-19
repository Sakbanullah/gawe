import { Table, Text } from "@mantine/core";

import { useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import type { PageState } from "../components/states";

export function ApplicationsPage() {
  const overview = useOverview();
  const state: PageState = overview.isPending ? "loading" : overview.isError ? "error" : "empty";

  return (
    <PageFrame
      title="Applications"
      description="Satu workspace per lowongan. CV dan cover letter dipisahkan."
      state={state}
      onRetry={() => void overview.refetch()}
    >
      <Table withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Lowongan</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Dokumen</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          <Table.Tr>
            <Table.Td colSpan={3}>
              <Text c="dimmed">Belum ada application.</Text>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </PageFrame>
  );
}
