import { test, expect, type Page } from "@playwright/test";

// ── Mock data ────────────────────────────────────────────────────────────────

const MOCK_JOBS = [
  {
    id: "job-1",
    url: "https://stripe.com/jobs/1",
    company_name: "Stripe",
    title: "Software Engineering Intern",
    location: ["San Francisco, CA"],
    is_remote: true,
    required_grad_year: 2027,
    grad_year_flexible: true,
    estimated_pay_hourly: 55,
    tech_stack: ["python", "ruby", "postgresql"],
    sponsors_visa: false,
    ai_extraction_status: "success",
    ai_confidence_score: 0.95,
    source: "ouckah",
    date_posted: "2025-07-01T00:00:00Z",
    date_ingested: "2025-07-02T00:00:00Z",
  },
  {
    id: "job-2",
    url: "https://meta.com/jobs/2",
    company_name: "Meta",
    title: "Data Engineering Intern",
    location: ["Menlo Park, CA", "Remote"],
    is_remote: true,
    required_grad_year: 2026,
    grad_year_flexible: false,
    estimated_pay_hourly: 48,
    tech_stack: ["python", "spark", "hive", "react"],
    sponsors_visa: true,
    ai_extraction_status: "success",
    ai_confidence_score: 0.88,
    source: "pittcsc",
    date_posted: "2025-06-28T00:00:00Z",
    date_ingested: "2025-06-29T00:00:00Z",
  },
  {
    id: "job-3",
    url: "https://openai.com/jobs/3",
    company_name: "OpenAI",
    title: "ML Research Intern",
    location: [],
    is_remote: null,
    required_grad_year: null,
    grad_year_flexible: null,
    estimated_pay_hourly: null,
    tech_stack: ["python", "pytorch"],
    sponsors_visa: null,
    ai_extraction_status: "partial",
    ai_confidence_score: 0.52,
    source: "ouckah",
    date_posted: null,
    date_ingested: "2025-07-03T00:00:00Z",
  },
];

const MOCK_JOB_DETAIL = {
  ...MOCK_JOBS[0],
  raw_description: "Stripe is looking for a software engineering intern...",
  date_processed: "2025-07-02T01:00:00Z",
};

const MOCK_STATS = {
  total: 3,
  by_source: { pittcsc: 1, ouckah: 2 },
  by_grad_year: { "2026": 1, "2027": 1 },
  by_status: { success: 2, partial: 1, failed: 0 },
};

async function mockApi(page: Page) {
  await page.route("**/api/jobs?**", async (route) => {
    const url = new URL(route.request().url());
    // Filter for remote_only test
    const remoteOnly = url.searchParams.get("remote_only") === "true";
    const data = remoteOnly
      ? MOCK_JOBS.filter((j) => j.is_remote === true)
      : MOCK_JOBS;

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        data,
        pagination: { page: 1, page_size: 25, total: data.length },
        cache_hit: false,
      }),
    });
  });

  await page.route("**/api/jobs/job-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_JOB_DETAIL),
    });
  });

  await page.route("**/api/jobs/**", async (route) => {
    const id = route.request().url().split("/api/jobs/")[1];
    const found = MOCK_JOBS.find((j) => j.id === id);
    if (found) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...found, raw_description: null, date_processed: null }),
      });
    } else {
      await route.fulfill({ status: 404 });
    }
  });

  await page.route("**/api/stats", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_STATS),
    });
  });
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("1. Page loads — logo and header visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("InternIQ")).toBeVisible();
});

test("2. Job cards render after load", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator('[data-testid="job-card"]');
  await expect(cards).toHaveCount(3, { timeout: 5000 });
});

test("3. Header shows total listing count from stats", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/3\s+listings/)).toBeVisible({ timeout: 5000 });
});

test("4. Clicking a card shows detail panel with View Original Posting link", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-testid="job-card"]').first().click();

  const detailPanel = page.locator('[data-testid="job-detail-panel"]');
  await expect(detailPanel).toBeVisible({ timeout: 5000 });

  const link = page.locator('[data-testid="view-posting-link"]');
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^https?:\/\//);
  await expect(link).toHaveAttribute("target", "_blank");
});

test("5. Detail panel shows job metadata", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-testid="job-card"]').first().click();
  const panel = page.locator('[data-testid="job-detail-panel"]');
  await expect(panel).toBeVisible({ timeout: 5000 });

  // Company name in the detail header
  await expect(panel.getByText("Stripe")).toBeVisible();
  // Pay
  await expect(panel.getByText("$55/hr")).toBeVisible();
  // Grad year
  await expect(panel.getByText("2027")).toBeVisible();
});

test("6. Null fields render as — and not as 'undefined' or '[object Object]'", async ({ page }) => {
  await page.goto("/");
  // Click the job with null fields (OpenAI - index 2)
  await page.locator('[data-testid="job-card"]').nth(2).click();
  await page.locator('[data-testid="job-detail-panel"]').waitFor({ state: "visible" });

  const bodyText = await page.locator('[data-testid="job-detail-panel"]').innerText();
  expect(bodyText).not.toContain("undefined");
  expect(bodyText).not.toContain("[object Object]");
  // Should have em-dashes for null pay and grad year
  expect(bodyText).toContain("—");
});

test("7. Filter bar is visible", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('[data-testid="filter-bar"]')).toBeVisible();
});

test("8. Grad year filter is present and selectable", async ({ page }) => {
  await page.goto("/");
  const select = page.locator('[data-testid="grad-year-select"]');
  await expect(select).toBeVisible();
  await select.selectOption("2027");
  await expect(select).toHaveValue("2027");
});

test("9. Tech stack input accepts tags via Enter key", async ({ page }) => {
  await page.goto("/");
  const input = page.locator('input[placeholder="Python, React…"]');
  await input.fill("python");
  await input.press("Enter");
  // The filter pill (with × remove button) should appear in the filter bar
  const filterBar = page.locator('[data-testid="filter-bar"]');
  await expect(filterBar.getByText(/python/)).toBeVisible();
});

test("10. Remote toggle can be clicked", async ({ page }) => {
  await page.goto("/");
  const toggle = page.locator('[data-testid="remote-toggle"] button[role="switch"]');
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
});

test("11. Clear button appears when filter is active and resets filters", async ({ page }) => {
  await page.goto("/");

  // No clear button initially
  await expect(page.getByText("Clear")).not.toBeVisible();

  // Set a grad year filter
  await page.locator('[data-testid="grad-year-select"]').selectOption("2027");
  const clearButton = page.getByRole("button", { name: /Clear/ });
  await expect(clearButton).toBeVisible();

  // Click Clear
  await clearButton.click();
  await expect(page.getByText("Clear")).not.toBeVisible();
  await expect(page.locator('[data-testid="grad-year-select"]')).toHaveValue("");
});

test("12. Keyboard navigation with ArrowDown selects next card", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-testid="job-card"]').first().click();

  // Focus the list panel and press ArrowDown
  const list = page.locator('[aria-label="Job listings"]');
  await list.focus();
  await list.press("ArrowDown");

  // The detail panel should now show Meta (index 1)
  const panel = page.locator('[data-testid="job-detail-panel"]');
  await expect(panel.getByText("Meta")).toBeVisible({ timeout: 3000 });
});

test("13. Switching between jobs updates the detail panel", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator('[data-testid="job-card"]');

  await cards.first().click();
  await expect(page.locator('[data-testid="job-detail-panel"]').getByText("Stripe")).toBeVisible();

  await cards.nth(1).click();
  await expect(page.locator('[data-testid="job-detail-panel"]').getByText("Meta")).toBeVisible({ timeout: 3000 });
});
