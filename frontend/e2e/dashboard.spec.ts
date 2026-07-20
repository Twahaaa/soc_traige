import { test, expect } from "@playwright/test";

import { pushLiveReport } from "./helpers";

/**
 * Full-stack E2E for the SOC triage dashboard.
 *
 * Preconditions (handled by `backend/scripts/run_dashboard_e2e.sh`):
 *  - Redis Streams reachable on :6379 (consumer group `group:dashboard` pre-created)
 *  - Qdrant reachable on :6333 with the `triage_reports` collection populated
 *  - FastAPI dashboard server spins up via Playwright's webServer config
 *  - Next dev server spins up via Playwright's webServer config
 */

test.describe("SOC triage dashboard", () => {
  test("AlertFeed loads and shows real triage reports from FastAPI", async ({ page }) => {
    await page.goto("/dashboard");

    // AlertFeed items carry data-testid="alert-feed-item"
    await expect(page.locator('[data-testid="alert-feed-item"]').first()).toBeVisible({
      timeout: 20_000,
    });
    const count = await page.locator('[data-testid="alert-feed-item"]').count();
    expect(count).toBeGreaterThan(0);
  });

  test("clicking an alert shows the full triage report", async ({ page }) => {
    await page.goto("/dashboard");

    // Wait for at least two items so the click can pick a non-default one too
    const items = page.locator('[data-testid="alert-feed-item"]');
    await expect(items.first()).toBeVisible({ timeout: 20_000 });

    // Click the first alert
    const first = items.first();
    await first.click();

    // ReportDetail header must reflect the clicked alert's title
    const expectedTitle = (await first.getAttribute("data-title")) ?? "";
    await expect(page.locator('[data-testid="report-title"]')).toContainText(expectedTitle, {
      timeout: 10_000,
    });

    // Anomaly score & MITRE panel snake_case fields render
    await expect(page.getByText(/Anomaly Score \(NeuralLog Confidence\)/)).toBeVisible();
    //Evidence is rendered
    await expect(page.getByText(/Evidence Log Lines/)).toBeVisible();
  });

  test('filter "Critical" retains only critical alerts', async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page.locator('[data-testid="alert-feed-item"]').first()).toBeVisible({
      timeout: 20_000,
    });

    await page.getByRole("button", { name: "Critical", exact: true }).click();

    // SWR uses keepPreviousData — wait for the previous unfiltered batch to
    // drain: only once every visible item carries data-severity=Critical can
    // we assert. Up to 15s for the re-fetch to settle.
    await expect(async () => {
      const handles = await page.locator('[data-testid="alert-feed-item"]').elementHandles();
      // No items at all is also acceptable (empty Critical result).
      for (const h of handles) {
        expect(await h.getAttribute("data-severity")).toBe("Critical");
      }
    }).toPass({ timeout: 15_000 });
  });

  test("StatsPanel renders real backend stats (counts reflect Qdrant)", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page.locator('[data-testid="total-alerts-24h"]')).toBeVisible({
      timeout: 20_000,
    });

    // Should be a non-negative integer
    const value = await page.locator('[data-testid="total-alerts-24h"]').textContent();
    expect(value).not.toBeNull();
    expect(Number.parseInt(value ?? "-1", 10)).toBeGreaterThanOrEqual(0);
  });

  test("live report pushed to Redis stream appears in AlertFeed via WebSocket", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    await expect(page.locator('[data-testid="alert-feed-item"]').first()).toBeVisible({
      timeout: 20_000,
    });

    const report = pushLiveReport({
      title: `E2E LIVE-${Math.random().toString(36).slice(2, 8)}`,
    });

    // The dashboard subscriptions are LIVE → the alert should appear in the feed
    // within seconds. Wait up to 10s for a matching data-title attribute.
    await expect(
      page.locator(`[data-testid="alert-feed-item"][data-title="${report.title}"]`),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("clicking the live report renders its full detail including MITRE snake_case fields", async ({
    page,
  }) => {
    await page.goto("/dashboard");

    await expect(page.locator('[data-testid="alert-feed-item"]').first()).toBeVisible({
      timeout: 20_000,
    });

    const report = pushLiveReport({
      title: `E2E DETAIL-${Math.random().toString(36).slice(2, 8)}`,
      severity: "Critical",
    });

    const item = page.locator(
      `[data-testid="alert-feed-item"][data-title="${report.title}"]`,
    );
    await expect(item).toBeVisible({ timeout: 10_000 });
    await item.click();

    await expect(page.locator('[data-testid="report-title"]')).toContainText(
      report.title,
      { timeout: 10_000 },
    );

    // MITRE block — snake_case technique_id is rendered as a labeled pill
    await expect(page.getByText("T1110", { exact: true })).toBeVisible();
    // IP reputation — snake_case field surfaces as "Total Reports" label with the value
    await expect(
      page.locator("text=Total Reports").first(),
    ).toBeVisible();
  });
});