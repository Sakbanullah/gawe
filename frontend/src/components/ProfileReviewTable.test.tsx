import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProfileVersion } from "../app/apiClient";
import { ProfileReviewTable } from "./ProfileReviewTable";

function profile(overrides: Partial<ProfileVersion> = {}): ProfileVersion {
  return {
    profile_id: "prof_1",
    profile_version_id: "pv_1",
    master_cv_id: "cv_1",
    version: 1,
    status: "in_review",
    schema_version: "1",
    content: {
      personal: { full_name: "Nadia Pratama" },
      experience: [
        {
          id: "exp_1",
          company: "PT Contoh",
          title: "Data Analyst",
          evidence: ["ev_1"],
          bullets: [{ id: "b_1", text: "Built weekly reports", evidence: ["ev_1"] }],
        },
      ],
    },
    evidence_index: {
      ev_1: {
        evidence_id: "ev_1",
        source: "cv",
        quote: "Data Analyst at PT Contoh",
        locator: { page: 1, block_id: "blk_1" },
      },
    },
    conflicts: [],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as ProfileVersion;
}

function renderTable(node: React.ReactNode) {
  return render(<MantineProvider>{node}</MantineProvider>);
}

describe("ProfileReviewTable", () => {
  it("shows the fact under a human label with its source quote", () => {
    renderTable(
      <ProfileReviewTable profile={profile()} onCorrect={() => undefined} onResolveConflict={() => undefined} />,
    );

    expect(screen.getByText("Pengalaman kerja")).toBeTruthy();
    expect(screen.getByText("Data Analyst")).toBeTruthy();
    expect(screen.getAllByText(/Data Analyst at PT Contoh/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/halaman 1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Dari CV").length).toBeGreaterThan(0);
    // Internal paths stay out of the visible table.
    expect(screen.queryByText("experience.exp_1")).toBeNull();
  });

  it("flags unresolved conflicts and blocks nothing silently", () => {
    renderTable(
      <ProfileReviewTable
        profile={profile({
          conflicts: [
            {
              conflict_id: "c_1",
              path: "experience.exp_1.title",
              candidates: [{ value: "Data Analyst" }, { value: "Senior Data Analyst" }],
            },
          ],
        })}
        onCorrect={() => undefined}
        onResolveConflict={() => undefined}
      />,
    );

    expect(screen.getByText("Ada data yang berbeda")).toBeTruthy();
    expect(screen.getByText("Senior Data Analyst")).toBeTruthy();
  });
});
