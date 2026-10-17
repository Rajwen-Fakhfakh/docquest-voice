import "@testing-library/jest-dom/vitest";

// jsdom n'implémente pas scrollIntoView (utilisé par ChatShell pour suivre la conversation).
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
