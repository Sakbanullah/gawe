import { Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

import { EmptyState, ErrorState, LoadingState, PartialState, type PageState } from "./states";

type Props = {
  title: string;
  description?: string;
  state: PageState;
  onRetry?: () => void;
  partialMessage?: string | null;
  children?: ReactNode;
};

export function PageFrame({
  title,
  description,
  state,
  onRetry,
  partialMessage,
  children,
}: Props) {
  return (
    <Stack gap="md">
      <div>
        <Title order={2}>{title}</Title>
        {description ? (
          <Text c="dimmed" size="sm">
            {description}
          </Text>
        ) : null}
      </div>
      {partialMessage ? <PartialState message={partialMessage} /> : null}
      {state === "loading" ? <LoadingState /> : null}
      {state === "error" ? <ErrorState onRetry={onRetry} /> : null}
      {state === "empty" ? <EmptyState message="Belum ada data untuk halaman ini." /> : null}
      {state === "ready" ? children : null}
    </Stack>
  );
}
