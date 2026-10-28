import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, ErrorState, LoadingState, StatusBadge } from "./states";

function renderWithMantine(node: React.ReactNode) {
  return render(<MantineProvider>{node}</MantineProvider>);
}

describe("shared states", () => {
  it("renders loading text", () => {
    renderWithMantine(<LoadingState />);
    expect(screen.getByText("Sedang memuat…")).toBeTruthy();
  });

  it("renders error with retry action", () => {
    renderWithMantine(<ErrorState onRetry={() => undefined} />);
    expect(screen.getByText("Data belum bisa dimuat")).toBeTruthy();
    expect(screen.getByText("Coba lagi")).toBeTruthy();
  });

  it("renders empty message", () => {
    renderWithMantine(<EmptyState message="Belum ada lowongan." />);
    expect(screen.getByText("Belum ada lowongan.")).toBeTruthy();
  });

  it("renders status as text, not colour alone", () => {
    renderWithMantine(
      <StatusBadge status="needs_review" label="Perlu kamu periksa" />,
    );
    expect(screen.getByText("Perlu kamu periksa")).toBeTruthy();
  });
});
