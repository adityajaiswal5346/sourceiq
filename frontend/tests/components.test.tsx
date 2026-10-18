/**
 * DocuMind — Frontend Unit Tests
 * Tests for UI components and auth context.
 * Uses Vitest + React Testing Library.
 * Zero `any` types. Accessibility assertions included.
 *
 * Run: npm test
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ConfidenceLabel } from "../types/api";

// ── ConfidenceBadge ────────────────────────────────────────────────

describe("ConfidenceBadge", () => {
  const { ConfidenceBadge } = await import("../components/ui");

  it("renders high confidence correctly", () => {
    render(<ConfidenceBadge label="high" score={0.87} />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("High · 87%");
    expect(badge).toHaveAttribute("aria-label", "high confidence, 87%");
  });

  it("renders medium confidence correctly", () => {
    render(<ConfidenceBadge label="medium" score={0.54} />);
    expect(screen.getByRole("status")).toHaveTextContent("Medium · 54%");
  });

  it("renders low confidence correctly", () => {
    render(<ConfidenceBadge label="low" score={0.18} />);
    expect(screen.getByRole("status")).toHaveTextContent("Low · 18%");
  });

  it("rounds percentage to nearest integer", () => {
    render(<ConfidenceBadge label="high" score={0.876} />);
    expect(screen.getByRole("status")).toHaveTextContent("88%");
  });

  const labels: ConfidenceLabel[] = ["high", "medium", "low"];
  it.each(labels)("applies correct colour class for %s", (label) => {
    render(<ConfidenceBadge label={label} score={0.5} />);
    const badge = screen.getByRole("status");
    // Each label should apply distinct styling
    expect(badge.className).toContain(
      label === "high"   ? "positive" :
      label === "medium" ? "warning"  : "danger"
    );
  });
});

// ── QueryCounter ───────────────────────────────────────────────────

describe("QueryCounter", () => {
  const { QueryCounter } = await import("../components/ui");

  it("shows remaining queries", () => {
    render(<QueryCounter remaining={2} limit={3} />);
    const counter = screen.getByRole("status");
    expect(counter).toHaveTextContent("2 of 3 remaining");
    expect(counter).toHaveAttribute("aria-label", "2 of 3 queries remaining");
  });

  it("shows limit reached when exhausted", () => {
    render(<QueryCounter remaining={0} limit={3} />);
    expect(screen.getByRole("status")).toHaveTextContent("Query limit reached");
  });

  it("never shows negative remaining", () => {
    render(<QueryCounter remaining={0} limit={3} />);
    const text = screen.getByRole("status").textContent ?? "";
    expect(text).not.toMatch(/-\d/);
  });
});

// ── SourcePanel ────────────────────────────────────────────────────

describe("SourcePanel", () => {
  const { default: SourcePanel } = await import("../components/SourcePanel");

  const mockCitations = [
    {
      source_file:  "pod-lifecycle.md",
      heading_path: "Pods > Pod Lifecycle > Termination",
      page:         0,
      citation:     "pod-lifecycle.md > Pods > Pod Lifecycle",
      confidence:   0.87,
    },
    {
      source_file:  "pods.md",
      heading_path: "Working with Pods",
      page:         0,
      citation:     "pods.md > Working with Pods",
      confidence:   0.42,
    },
  ] as const;

  it("renders nothing when citations are empty", () => {
    const { container } = render(<SourcePanel citations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders correct number of citations", () => {
    render(<SourcePanel citations={mockCitations} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("displays source filenames", () => {
    render(<SourcePanel citations={mockCitations} />);
    expect(screen.getByText("pod-lifecycle.md")).toBeInTheDocument();
    expect(screen.getByText("pods.md")).toBeInTheDocument();
  });

  it("displays heading paths", () => {
    render(<SourcePanel citations={mockCitations} />);
    expect(screen.getByText(/Pods > Pod Lifecycle > Termination/)).toBeInTheDocument();
  });

  it("displays relevance percentage", () => {
    render(<SourcePanel citations={mockCitations} />);
    expect(screen.getByText("87% relevance")).toBeInTheDocument();
  });

  it("has accessible section label", () => {
    render(<SourcePanel citations={mockCitations} />);
    expect(screen.getByRole("region", { name: "Sources" })).toBeInTheDocument();
  });
});

// ── ApiError ───────────────────────────────────────────────────────

describe("ApiError", () => {
  it("carries status code", async () => {
    const { ApiError } = await import("../api/client");
    const err = new ApiError("Not found", 404);
    expect(err.statusCode).toBe(404);
    expect(err.message).toBe("Not found");
    expect(err.name).toBe("ApiError");
  });

  it("is instanceof Error", async () => {
    const { ApiError } = await import("../api/client");
    expect(new ApiError("test", 500)).toBeInstanceOf(Error);
  });
});

// ── AuthContext ────────────────────────────────────────────────────

describe("AuthContext", () => {
  it("throws when used outside provider", async () => {
    const { useAuth } = await import("../context/AuthContext");
    const { renderHook } = await import("@testing-library/react");

    // Suppress React error boundary console output
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be called within <AuthProvider />"
    );
    spy.mockRestore();
  });
});
