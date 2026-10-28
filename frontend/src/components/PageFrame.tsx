import { Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

import { EmptyState, ErrorState, LoadingState, PartialState, type PageState } from "./states";

type Props = {
  title: string;
  description?: string;
  /** Short line above the title: where the user is. */
  eyebrow?: string;
  state: PageState;
  onRetry?: () => void;
  partialMessage?: string | null;
  children?: ReactNode;
  /** Primary action for this screen. */
  action?: ReactNode;
};

/**
 * Every page answers three questions without scrolling: where am I, what can I
 * do here, and what should I do next.
 */
export function PageFrame({
  title,
  description,
  eyebrow,
  state,
  onRetry,
  partialMessage,
  children,
  action,
}: Props) {
  return (
    <Stack gap="lg">
      <Stack gap={4}>
        {eyebrow ? (
          <Text size="xs" fw={600} tt="uppercase" c="dimmed">
            {eyebrow}
          </Text>
        ) : null}
        <Group justify="space-between" align="flex-start" gap="md" wrap="wrap">
          <div>
            <Title order={1}>{title}</Title>
            {description ? (
              <Text c="dimmed" mt={6} maw={680}>
                {description}
              </Text>
            ) : null}
          </div>
          {action}
        </Group>
      </Stack>
      {partialMessage ? <PartialState message={partialMessage} /> : null}
      {state === "loading" ? <LoadingState /> : null}
      {state === "error" ? <ErrorState onRetry={onRetry} /> : null}
      {state === "empty" ? (
        <EmptyState message={description ?? "Belum ada data untuk halaman ini."} />
      ) : null}
      {state === "ready" ? children : null}
    </Stack>
  );
}
