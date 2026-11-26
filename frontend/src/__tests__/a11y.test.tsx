import { describe, it, expect, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "../lib/api/queryClient";
import { AppProvider } from "../context/AppContext";

import { OverviewPage } from "../pages/OverviewPage";
import { AskPage } from "../pages/AskPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { SettingsPage } from "../pages/SettingsPage";

function renderWithContext(component: React.ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppProvider>{component}</AppProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

const routes = [
  { name: "OverviewPage", component: <OverviewPage /> },
  { name: "AskPage", component: <AskPage /> },
  { name: "DocumentsPage", component: <DocumentsPage /> },
  { name: "SettingsPage", component: <SettingsPage /> },
];

describe("Accessibility WCAG AA Audits (Dark & Light Themes)", () => {
  for (const theme of ["dark", "light"] as const) {
    describe(`Theme: ${theme}`, () => {
      beforeEach(() => {
        localStorage.setItem("grant_theme", theme);
        if (theme === "dark") {
          document.documentElement.classList.add("dark");
        } else {
          document.documentElement.classList.remove("dark");
        }
      });

      for (const route of routes) {
        it(`${route.name} passes accessibility audit in ${theme} mode`, async () => {
          const { container } = renderWithContext(route.component);
          const results = await axe(container);
          expect(results.violations).toEqual([]);
        });
      }
    });
  }
});
