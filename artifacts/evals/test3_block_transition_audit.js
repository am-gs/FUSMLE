const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND = "https://usmaili.vercel.app";
const outDir = path.join(
  process.cwd(),
  "artifacts",
  "evals",
  "test3_block_transition_output",
);
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const result = { checks: {} };

  try {
    const unique = Date.now();
    const email = `test3.block.${unique}@example.com`;
    const password = "Test3Audit!123";
    result.user = { email };

    await page.goto(`${FRONTEND}/index.html`, { waitUntil: "networkidle" });
    await page.click("#showRegister");
    await page.fill("#registerName", "Test3 Block Audit");
    await page.fill("#registerEmail", email);
    await page.fill("#registerPassword", password);
    await Promise.all([
      page.waitForURL(/dashboard\.html/, { timeout: 30000 }),
      page.locator('#registerForm button[type="submit"]').click(),
    ]);

    await page.goto(`${FRONTEND}/createtest.html`, {
      waitUntil: "networkidle",
    });
    await page.locator("#generateTest3Btn").click();
    await page.waitForURL(/qbank\.html\?session=/, { timeout: 60000 });
    result.startUrl = page.url();

    for (let i = 0; i < 20; i++) {
      await page.waitForSelector(".option-item", { timeout: 30000 });
      await page.locator(".option-item").first().click();
      await page.locator("#submitBtn").click();
      await page.waitForLoadState("networkidle");
      if (i < 19) {
        await page.waitForFunction(
          () => {
            const el = document.querySelector("#questionPosition");
            return el && /Question\s+\d+\s+of\s+20/.test(el.textContent || "");
          },
          { timeout: 30000 },
        );
      } else {
        await page.waitForSelector("#nextBtn", { timeout: 30000 });
        const nextText =
          (await page.locator("#nextBtn").textContent())?.trim() || "";
        result.finalQuestionCta = nextText;
        await page.locator("#nextBtn").click();
        await page.waitForSelector("#completeState", { timeout: 30000 });
      }
    }

    const completeTitle =
      (await page.locator("#completeTitle").textContent())?.trim() || "";
    const completeStats =
      (await page.locator("#completeStats").textContent())?.trim() || "";
    const completeButtons = await page
      .locator("#completeButtons button")
      .allTextContents();
    result.blockComplete = { completeTitle, completeStats, completeButtons };
    result.checks.block1CompleteScreen = completeTitle === "Block 1 Complete";
    result.checks.intermediateScoreHidden =
      /recorded/i.test(completeStats) && !/%/.test(completeStats);

    const startBlock2Button = page
      .locator("#completeButtons button", { hasText: "Start Block 2" })
      .first();
    result.checks.startBlock2ButtonPresent = await startBlock2Button
      .count()
      .then((n) => n > 0);
    await Promise.all([
      page.waitForURL(/block=2/, { timeout: 30000 }),
      startBlock2Button.click(),
    ]);
    await page.waitForLoadState("networkidle");

    const blockBadge =
      (await page.locator("#blockBadge").textContent())?.trim() || "";
    const questionPosition =
      (await page.locator("#questionPosition").textContent())?.trim() || "";
    result.block2 = { url: page.url(), blockBadge, questionPosition };
    result.checks.block2Loads =
      /Block 2 of 6/.test(blockBadge) &&
      questionPosition === "Question 1 of 20";

    await page.screenshot({
      path: path.join(outDir, "block2.png"),
      fullPage: true,
    });
  } catch (error) {
    result.error = { message: error.message, stack: error.stack };
    try {
      await page.screenshot({
        path: path.join(outDir, "failure.png"),
        fullPage: true,
      });
    } catch (_) {}
  } finally {
    fs.writeFileSync(
      path.join(outDir, "result.json"),
      JSON.stringify(result, null, 2),
    );
    await browser.close();
  }
})();
