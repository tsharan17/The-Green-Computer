import { type Page, expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

const PASSWORD = "an e2e test passphrase";
let n = 0;
const email = (tag: string) => `${tag}-${Date.now()}-${n++}@example.com`;

async function signUp(page: Page, who: string) {
  await page.goto("/#/signup");
  await page.getByLabel("Your name (optional)").fill("E2E");
  await page.getByLabel("Email").fill(who);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
}

async function openExample(page: Page): Promise<string> {
  await page.getByRole("link", { name: /Example: YOLOv8s on a robot/ }).click();
  await expect(page).toHaveURL(/#\/p\/\d+\/input/);
  return page.url().match(/#\/p\/(\d+)/)![1];
}

test("sign-up, analysis, design plan, comparison, export and history", async ({ page }) => {
  await signUp(page, email("journey"));
  const pid = await openExample(page);

  await page.getByRole("button", { name: "Analyse", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`#/p/${pid}/recommendations`));
  await expect(page.getByText(/Your current setup fails/)).toBeVisible();

  // Build, analyse and save a plan.
  await page.getByRole("tab", { name: "Build a design plan" }).click();
  await page.getByRole("button", { name: /Analyse this plan/ }).click();
  await expect(page.getByRole("heading", { name: "Today vs the plan" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Each change on its own" })).toBeVisible();
  await page.getByLabel("Name").fill("E2E plan");
  await page.getByRole("button", { name: "Save plan" }).click();
  await expect(page.getByText(/Saved “E2E plan” as version 1/)).toBeVisible();
  await page.getByRole("tab", { name: "Saved plans" }).click();
  await expect(page.getByRole("cell", { name: /E2E plan/ })).toBeVisible();

  // The analysis screens render from the stored analysis.
  await page.goto(`/#/p/${pid}/system-map`);
  await expect(page.getByRole("heading", { name: "System map" })).toBeVisible();
  await expect(page.getByText("Predicted by the analytical engine", { exact: true })).toBeVisible();
  await page.goto(`/#/p/${pid}/thermal`);
  await expect(page.getByRole("heading", { name: "Cooling options for this workload" })).toBeVisible();

  // Export: a generated report and a plan file download (the PDF itself is checked by the API tests;
  // Edge opens downloaded PDFs in a tab of its own, which would leak into later tests).
  await page.goto(`/#/p/${pid}/verify`);
  await page.getByRole("tab", { name: "Export" }).click();
  const report = page.locator(".export-list li", { hasText: "Engineering report (Markdown)" });
  const dl = page.waitForEvent("download");
  await report.getByRole("button", { name: "Download" }).click();
  const md = await dl;
  expect(md.suggestedFilename()).toMatch(/report\.md$/);
  expect(await md.failure()).toBeNull(); // waits until the file is fully written
  const planRow = page.locator(".export-list li", { hasText: "Design plan (JSON)" });
  const dl2 = page.waitForEvent("download");
  await planRow.getByRole("button", { name: "Download" }).click();
  const planFile = await dl2;
  expect(planFile.suggestedFilename()).toMatch(/plan-e2e-plan-v1\.json$/);
  expect(await planFile.failure()).toBeNull();
  await expect(page.getByRole("heading", { name: "Export history" })).toBeVisible();

  // History records versions, the analysis and the exports.
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByRole("heading", { name: "Input versions" })).toBeVisible();
  await expect(page.locator(".audit").getByText("Analysis run").first()).toBeVisible();
  await expect(page.locator(".audit").getByText("Exported").first()).toBeVisible();
});

test("upload an ONNX model and get an honest answer for unsupported files", async ({ page }) => {
  await signUp(page, email("upload"));
  await openExample(page);
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles(path.join(here, "fixtures", "tiny.onnx"));
  const item = page.locator(".intake-item", { hasText: "tiny.onnx" });
  await expect(item.getByText("valid", { exact: true })).toBeVisible();
  await expect(item.getByText("Selected as the project's model.")).toBeVisible();
  await expect(item.getByText("Graph summary")).toBeVisible();

  await page.getByRole("tab", { name: "FPGA" }).click();
  const chooser2 = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser2).setFiles({ name: "core.sv", mimeType: "text/plain", buffer: Buffer.from("module m; endmodule") });
  const sv = page.locator(".intake-item", { hasText: "core.sv" });
  await expect(sv.getByText("unsupported", { exact: true })).toBeVisible();
  await expect(sv.getByText(/What works today:.*report_utilization|What works today:.*Vivado/)).toBeVisible();
});

test("sign out and back in; a wrong password is refused", async ({ page }) => {
  const who = email("session");
  await signUp(page, who);
  await page.getByRole("button", { name: "E2E" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(who);
  await page.getByLabel("Password").fill("not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("incorrect");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Welcome|workspace/ })).toBeVisible();
});

test("one account cannot open another account's project", async ({ browser }) => {
  const a = await browser.newContext();
  const pa = await a.newPage();
  await signUp(pa, email("owner"));
  const pid = await openExample(pa);

  const b = await browser.newContext();
  const pb = await b.newPage();
  await signUp(pb, email("other"));
  await pb.goto(`/#/p/${pid}/input`);
  await expect(pb.getByRole("heading", { name: "Project not found" })).toBeVisible();
  const r = await pb.request.get(`/api/v1/projects/${pid}`);
  expect(r.status()).toBe(404);
  await a.close();
  await b.close();
});

test("account deletion signs out and removes access", async ({ page }) => {
  const who = email("delete");
  await signUp(page, who);
  await page.goto("/#/account");
  await page.getByLabel("Password", { exact: true }).last().fill(PASSWORD);
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete my account" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(who);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("incorrect");
});
