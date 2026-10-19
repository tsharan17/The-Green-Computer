import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/** WCAG 2.1 A/AA checks with axe-core on the main screens, in light and dark colour schemes. */
const SCREENS = ["input", "constraints", "system-map", "timeline", "memory", "thermal", "energy", "recommendations", "verify"];

for (const scheme of ["light", "dark"] as const) {
  test(`main screens have no WCAG A/AA violations (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto("/#/signin");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    const scan = async (where: string) => {
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const found = r.violations.map((v) => `${where}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target.join(" ")}`);
      expect(found, found.join("\n")).toEqual([]);
    };
    await scan("sign-in");
    await page.goto("/#/signup");
    await page.getByLabel("Email").fill(`a11y-${scheme}-${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("an accessibility test passphrase");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
    await scan("workspace");
    await page.getByRole("link", { name: /Example: YOLOv8s/ }).click();
    const pid = page.url().match(/#\/p\/(\d+)/)![1];
    await page.getByRole("button", { name: "Analyse", exact: true }).click();
    await expect(page.getByText(/Your current setup fails/)).toBeVisible();
    for (const s of SCREENS) {
      await page.goto(`/#/p/${pid}/${s}`);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main h1")).toBeVisible();
      await scan(s);
    }
    await page.goto("/#/account");
    await scan("account");
    await page.goto("/#/capabilities");
    await page.waitForLoadState("networkidle");
    await scan("capabilities");
  });
}
