import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(cleanup);

// jsdom lacks matchMedia; Mantine reads it for colour scheme.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

if (!document.fonts) {
  // jsdom lacks document.fonts; Mantine TextareaAutosize listens on it.
  Object.defineProperty(document, "fonts", {
    value: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
  });
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
