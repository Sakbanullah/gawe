import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as queries from "../app/queries";
import { DocumentReviewPanel } from "./DocumentReviewPanel";

const mutateAsync = vi.fn();

vi.mock("../app/queries", () => ({
  useDocumentVersion: () => ({
    data: {
      document_version_id: "docv_1",
      content_hash: "hash-1",
      status: "in_review",
      review_status: "completed",
      approved: false,
      content: {},
      diff: {},
      findings_summary: null,
    },
    isError: false,
    error: null,
    isPending: false,
  }),
  useDocumentFindings: () => ({
    data: {
      verdict: "changes_required",
      findings: [
        {
          finding_id: "fnd_001",
          severity: "blocker",
          category: "factuality",
          problem: "Evidence id tidak ditemukan.",
          quote: "Built payments.",
        },
        {
          finding_id: "fnd_002",
          severity: "major",
          category: "factuality",
          problem: "Klaim tanpa evidence.",
          quote: "Led migration.",
        },
        {
          finding_id: "fnd_003",
          severity: "nit",
          category: "style",
          problem: "Gaya kalimat.",
          quote: "Kecil.",
        },
      ],
    },
  }),
  useRunDocumentReview: () => ({ mutateAsync, isPending: false }),
  useApproveDocument: () => ({ mutateAsync, isPending: false }),
  useCreateDocumentRevision: () => ({ mutateAsync, isPending: false }),
  useRequestDocumentRevision: () => ({ mutateAsync, isPending: false }),
  useCreateExport: () => ({ mutateAsync, isPending: false }),
  useExports: () => ({ data: { items: [] } }),
}));

function renderPanel() {
  return render(
    <MantineProvider>
      <DocumentReviewPanel applicationId="app_1" documentVersionId="docv_1" onClose={() => {}} />
    </MantineProvider>,
  );
}

describe("DocumentReviewPanel revision checkboxes", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({});
  });

  it("preselects blocker and major but not nit", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.queryByText("Evidence id tidak ditemukan.")).not.toBeNull(),
    );
    const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes.map((box) => box.checked)).toEqual([true, true, false]);
  });

  it("sends only the checked findings", async () => {
    renderPanel();
    await screen.findByText("Klaim tanpa evidence.");
    const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    fireEvent.click(boxes[1]); // uncheck the major
    fireEvent.click(screen.getByRole("button", { name: "Minta Gawe perbaiki yang dicentang" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(vi.mocked(queries.useRequestDocumentRevision)).toBeDefined();
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      applicationId: "app_1",
      documentVersionId: "docv_1",
      contentHash: "hash-1",
      findingIds: ["fnd_001"],
    });
  });
});

