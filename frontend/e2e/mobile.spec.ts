import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/** A phone (375 px) journey: every screen fits the width, wide charts and tables scroll inside their
 * own card, and axe finds nothing in either colour scheme. Also checks the installable-app files. */
test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });

const SCREENS = ["summary", "input", "constraints", "check", "system-map", "timeline", "memory", "thermal", "energy", "recommendations", "verify"];

/** Elements that stick out past the right edge of the screen, outside any scrolling container. */
async function overflow(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > vw + 1) out.push(`page is ${document.documentElement.scrollWidth}px wide`);
    const clipped = (el: Element) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") return true;
      }
      return false;
    };
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > vw + 1 && !clipped(el) && getComputedStyle(el).position !== "fixed") {
        const id = el.id ? `#${el.id}` : "";
        const cls = typeof el.className === "string" && el.className ? `.${el.className.trim().split(/\s+/).join(".")}` : "";
        out.push(`${el.tagName.toLowerCase()}${id}${cls} right=${Math.round(r.right)}`);
      }
    }
    return out.slice(0, 8);
  });
}

for (const scheme of ["light", "dark"] as const) {
  test(`phone journey fits the screen and passes axe (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const problems: string[] = [];
    const check = async (where: string) => {
      problems.push(...(await overflow(page)).map((o) => `${where}: ${o}`));
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      problems.push(...r.violations.map((v) => `${where}: axe ${v.id} ${v.nodes[0]?.target.join(" ")}`));
    };

    await page.goto("/#/");
    await expect(page.getByRole("heading", { name: /Will your AI model run well/ })).toBeVisible();
    await check("landing");
    await page.goto("/#/try/robot-vision");
    await expect(page.getByRole("heading", { name: "The answer" })).toBeVisible({ timeout: 30_000 });
    await check("try");
    await page.goto("/#/how");
    await expect(page.getByRole("heading", { name: "How we estimate", level: 1 })).toBeVisible();
    await check("how");
    await page.goto("/#/signin");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await check("sign-in");

    await page.goto("/#/signup");
    await page.getByLabel("Email").fill(`phone-${scheme}-${Date.now()}@example.com`);
    await page.getByLabel("Password").fill("a phone layout test passphrase");
    await page.getByRole("checkbox", { name: /I have read and accept/ }).check();
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByRole("heading", { name: "Start a new analysis" })).toBeVisible();
    await check("guided start");
    await page.goto("/#/");
    await expect(page.getByRole("heading", { name: /Find out whether/ })).toBeVisible();
    await check("workspace");
    await page.getByRole("link", { name: /Example: YOLOv8s/ }).click();
    const pid = page.url().match(/#\/p\/(\d+)/)![1];
    await page.getByRole("region", { name: "Decision summary" }).getByRole("button", { name: /^Analyse/ }).click();
    await expect(page.getByText(/today it is predicted to miss/)).toBeVisible();
    for (const s of SCREENS) {
      await page.goto(`/#/p/${pid}/${s}`);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("main h1")).toBeVisible();
      await check(s);
    }
    await page.goto("/#/account");
    await check("account");
    expect(problems, problems.join("\n")).toEqual([]);
  });
}

test("the app can be installed: manifest, icons and a shell-only service worker", async ({ page, request }) => {
  const m = await (await request.get("/manifest.webmanifest")).json();
  expect(m).toMatchObject({ name: "The Green Computer", display: "standalone", start_url: "/#/" });
  for (const icon of m.icons) expect((await request.get(icon.src)).ok(), icon.src).toBe(true);
  expect(m.icons.some((i: { purpose: string }) => i.purpose === "maskable")).toBe(true);

  await page.goto("/#/");
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
  expect(scope).toMatch(/\/$/);
  // The worker caches the shell, never the API.
  await page.goto("/#/try/edge-camera");
  await expect(page.getByRole("heading", { name: "The answer" })).toBeVisible({ timeout: 30_000 });
  const cached = await page.evaluate(async () => {
    const keys = await Promise.all((await caches.keys()).map(async (k) => (await (await caches.open(k)).keys()).map((r) => r.url)));
    return keys.flat();
  });
  expect(cached.length).toBeGreaterThan(0);
  expect(cached.filter((u) => u.includes("/api/"))).toEqual([]);
});
