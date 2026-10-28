import { Alert, Box, Button, Group, Loader, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

export type PageState = "loading" | "error" | "empty" | "ready";

export function LoadingState({ label = "Sedang memuat…" }: { label?: string }) {
  return (
    <Group gap="sm" py="lg" role="status">
      <Loader size="sm" />
      <Text size="sm" c="dimmed">
        {label}
      </Text>
    </Group>
  );
}

export function ErrorState({
  onRetry,
  title = "Data belum bisa dimuat",
  message = "Ada masalah saat mengambil data. Data yang sudah tersimpan tetap aman.",
}: {
  onRetry?: () => void;
  title?: string;
  message?: string;
}) {
  return (
    <Alert color="red" title={title}>
      <Stack gap="sm" align="flex-start">
        <Text size="sm">{message}</Text>
        {onRetry ? (
          <Button variant="light" color="red" onClick={onRetry}>
            Coba lagi
          </Button>
        ) : null}
      </Stack>
    </Alert>
  );
}

export function EmptyState({
  title = "Belum ada isinya",
  message,
  action,
}: {
  title?: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <Alert color="gray" variant="light" title={title}>
      <Stack gap="sm" align="flex-start">
        <Text size="sm">{message}</Text>
        {action}
      </Stack>
    </Alert>
  );
}

export function PartialState({ message }: { message: string }) {
  return (
    <Alert color="yellow" title="Datanya belum lengkap">
      <Text size="sm">{message}</Text>
    </Alert>
  );
}

const STATUS_COLOR: Record<string, string> = {
  approved: "teal",
  confirmed: "teal",
  completed: "teal",
  exported: "teal",
  failed: "red",
  ineligible: "red",
  broken: "red",
  outdated: "orange",
  needs_review: "orange",
  partial: "orange",
  restricted: "orange",
};

function dotColor(color: string): string {
  const map: Record<string, string> = {
    teal: "var(--mantine-color-teal-6)",
    red: "var(--mantine-color-red-6)",
    orange: "var(--mantine-color-orange-6)",
    gray: "var(--mantine-color-gray-5)",
  };
  return map[color] ?? map.gray;
}

/**
 * Status always carries words, so colour is never the only signal
 * (UI-DESIGN.md §6).
 */
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <Group gap={6} wrap="nowrap" component="span">
      <Box
        aria-hidden
        w={8}
        h={8}
        style={{
          borderRadius: 999,
          background: dotColor(STATUS_COLOR[status] ?? "gray"),
          flexShrink: 0,
        }}
      />
      <Text size="sm" span>
        {label ?? status}
      </Text>
    </Group>
  );
}
