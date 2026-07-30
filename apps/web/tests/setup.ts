import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom implements no layout, so scrollIntoView does not exist. Components that
// keep a thread scrolled to the newest message are correct to call it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom ships no EventSource. Components that follow a build's progress open one
// on mount, so without this the constructor throws inside an effect and the run
// reports an unhandled error even though every assertion passes.
if (!("EventSource" in globalThis)) {
  class StubEventSource {
    onmessage: ((event: MessageEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    close() {}
  }
  // Configurable, so a test that wants a real mock can still stub over it.
  Object.defineProperty(globalThis, "EventSource", {
    value: StubEventSource,
    writable: true,
    configurable: true,
  });
}

afterEach(() => {
  cleanup();
});
