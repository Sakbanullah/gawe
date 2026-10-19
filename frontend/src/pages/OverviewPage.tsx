import { Badge, Card, Group, SimpleGrid, Stack, Text } from "@mantine/core";

import { useOverview } from "../app/queries";
import { PageFrame } from "../components/PageFrame";
import type { PageState } from "../components/states";

export function OverviewPage() {
  const overview = useOverview();
  const state: PageState = overview.isPending
    ? "loading"
    : overview.isError
      ? "error"
      : overview.data
        ? "ready"
        : "empty";

  return (
    <PageFrame
      title="Overview"
      description="Status ringkas dan langkah berikutnya. Semua nilai dihitung backend."
      state={state}
      onRetry={() => void overview.refetch()}
    >
      {overview.data ? (
        <Stack gap="md">
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <Card withBorder>
              <Text size="sm" c="dimmed">
                Eligible
              </Text>
              <Text size="xl">{overview.data.counts.eligible}</Text>
            </Card>
            <Card withBorder>
              <Text size="sm" c="dimmed">
                Needs review
              </Text>
              <Text size="xl">{overview.data.counts.needs_review}</Text>
            </Card>
            <Card withBorder>
              <Text size="sm" c="dimmed">
                Ineligible
              </Text>
              <Text size="xl">{overview.data.counts.ineligible}</Text>
            </Card>
          </SimpleGrid>
          <Card withBorder>
            <Group justify="space-between">
              <div>
                <Text fw={500}>{overview.data.next_action.label ?? "Langkah berikutnya"}</Text>
                <Text size="sm" c="dimmed">
                  {overview.data.next_action.code}
                </Text>
              </div>
              <Badge variant="light">
                {overview.data.provider_configured ? "provider configured" : "provider belum dikonfigurasi"}
              </Badge>
            </Group>
          </Card>
        </Stack>
      ) : null}
    </PageFrame>
  );
}
