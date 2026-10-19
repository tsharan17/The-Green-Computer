import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** The real device agent (agent/gc_agent.py) paired from the UI and run in simulator mode. */
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const agent = path.join(root, "agent", "gc_agent.py");
const python = process.env.GC_PYTHON
  ?? [path.join(root, "backend", ".venv", "Scripts", "python.exe"), path.join(root, "backend", ".venv", "bin", "python")].find(existsSync)
  ?? "python3";

test("register a device, pair the agent, approve a run, see a labelled result", async ({ page, baseURL }) => {
  const who = `device-${Date.now()}@example.com`;
  await page.goto("/#/signup");
  await page.getByLabel("Email").fill(who);
  await page.getByLabel("Password").fill("an e2e test passphrase");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Start a new analysis" })).toBeVisible();
  await page.goto("/#/");
  await page.getByRole("link", { name: /Example: YOLOv8s on a robot/ }).click();
  const pid = page.url().match(/#\/p\/(\d+)/)![1];

  // An approved file must be a validated ONNX model of this project.
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose files" }).click();
  await (await chooser).setFiles(path.join(here, "fixtures", "tiny.onnx"));
  await expect(page.locator(".intake-item", { hasText: "tiny.onnx" }).getByText("valid", { exact: true })).toBeVisible();

  await page.goto(`/#/p/${pid}/verify?tab=device`);
  await page.getByLabel("Device name").fill("E2E bench board");
  await page.getByRole("button", { name: "Register and get a pairing code" }).click();
  const code = (await page.locator(".code-big").textContent())!.trim();
  expect(code).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);

  const home = mkdtempSync(path.join(os.tmpdir(), "gc-agent-"));
  execFileSync(python, [agent, "--home", home, "pair", "--server", baseURL!, "--code", code], { stdio: "pipe" });
  await page.getByRole("button", { name: "Done" }).click();
  await page.reload();
  await expect(page.locator(".outcome", { hasText: "online" })).toBeVisible();

  await page.getByRole("button", { name: "Approve and send" }).click();
  await expect(page.locator(".job-list li").first()).toContainText("queued");
  execFileSync(python, [agent, "--home", home, "run", "--once", "--simulate"], { stdio: "pipe" });
  await page.reload();
  const job = page.locator(".job-list li").first();
  await expect(job).toContainText("succeeded");
  await expect(job.locator(".tag")).toHaveText(/simulated/);
  await expect(job).toContainText("never imported as a measurement");

  // Revoking stops the agent at once.
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.locator(".outcome", { hasText: "revoked" })).toBeVisible();
  expect(() => execFileSync(python, [agent, "--home", home, "run", "--once"], { stdio: "pipe" })).toThrow();
});
