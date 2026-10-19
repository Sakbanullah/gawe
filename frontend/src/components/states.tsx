import { Alert, Badge, Button, Group, Loader, Stack, Text } from "@mantine/core";

export type PageState = "loading" | "error" | "empty" | "ready";

export function LoadingState() {
  return (
    <Group>
      <Loader size="sm" />
      <Text>Memuat…</Text>
    </Group>
  );
}

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  return (
    <Alert color="red" title="Gagal memuat data">
      <Stack gap="xs">
        <Text>Permintaan tidak dapat diselesaikan.</Text>
        {onRetry ? (
          <Button variant="light" onClick={onRetry}>
            Coba lagi
          </Button>
        ) : null}
      </Stack>
    </Alert>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <Alert color="gray" title="Belum ada data">
      {message}
    </Alert>
  );
}

export function PartialState({ message }: { message: string }) {
  return (
    <Alert color="yellow" title="Hasil sebagian">
      {message}
    </Alert>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="light" color="gray">
      {status}
    </Badge>
  );
}
