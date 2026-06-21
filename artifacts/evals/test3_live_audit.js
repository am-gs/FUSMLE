const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND = "https://usmaili.vercel.app";
const outDir = path.join(
  process.cwd(),
  "artifacts",
  "evals",
  "test3_live_audit_output",
);
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleMessages = [];
  const requestFailures = [];
  const responseFailures = [];

  page.on("console", (msg) => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });
  page.on("requestfailed", (req) => {
    requestFailures.push({
      url: req.url(),
      method: req.method(),
      failure: req.failure(),
    });
  });
  page.on("response", (res) => {
    if (res.status() >= 400) {
      responseFailures.push({
        url: res.url(),
        status: res.status(),
        statusText: res.statusText(),
      });
    }
  });

  const result = {
    frontend: FRONTEND,
    checks: {},
    consoleMessages,
    requestFailures,
    responseFailures,
  };

  try {
    const unique = Date.now();
    const email = `test3.audit.${unique}@example.com`;
    const password = "Test3Audit!123";
    const name = "Test3 Audit";
    result.user = { email };

    await page.goto(`${FRONTEND}/index.html`, { waitUntil: "networkidle" });
    await page.click("#showRegister");
    await page.fill("#registerName", name);
    await page.fill("#registerEmail", email);
    await page.fill("#registerPassword", password);
    await Promise.all([
      page.wait_for_url
        ? page.wait_for_url(/dashboard\.html/)
        : page.waitForURL(/dashboard\.html/),
      page.locator('#registerForm button[type="submit"]').click(),
    ]).catch(async () => {
      await page.waitForURL(/dashboard\.html/, { timeout: 20000 });
    });
    result.checks.registerAndRedirect = page.url().includes("dashboard.html");

    await page.goto(`${FRONTEND}/createtest.html`, {
      waitUntil: "networkidle",
    });
    await page.locator("#generateTest3Btn").click();
    await page.waitForURL(/qbank\.html\?session=/, { timeout: 60000 });
    result.qbankUrl = page.url();
    result.checks.launchTest3 = /exam=test3/.test(page.url());

    await page.waitForLoadState("networkidle");
    await page.waitForSelector("#questionPosition");
    const questionPosition1 =
      (await page.locator("#questionPosition").textContent())?.trim() || "";
    const navCount = await page.locator(".nav-dot").count();
    const itemId =
      (
        await page.locator(".fred-top .grp .fred-item-id").nth(2).textContent()
      )?.trim() || "";
    const renderFlagVisible = await page
      .locator("#renderFlag")
      .isVisible()
      .catch(() => false);
    const renderFlagText = renderFlagVisible
      ? ((await page.locator("#renderFlag").textContent()) || "").trim()
      : null;

    let imageVisible = false;
    let imageSrc = null;
    const imageLocator = page.locator("#imageContainer img").first();
    if (await imageLocator.count()) {
      await imageLocator
        .waitFor({ state: "visible", timeout: 15000 })
        .catch(() => {});
      imageVisible = await imageLocator.isVisible().catch(() => false);
      imageSrc = await imageLocator.getAttribute("src").catch(() => null);
    }

    result.firstQuestion = {
      questionPosition: questionPosition1,
      navCount,
      itemId,
      renderFlagVisible,
      renderFlagText,
      imageVisible,
      imageSrc,
    };
    result.checks.blockQuestionCount20 =
      questionPosition1 === "Question 1 of 20" && navCount === 20;

    const optionCount = await page.locator(".option-item").count();
    result.firstQuestion.optionCount = optionCount;
    if (optionCount > 0) {
      await page.locator(".option-item").first().click();
      await page.locator("#submitBtn").click();
      await page.waitForTimeout(2000);
      await page.waitForLoadState("networkidle");
    }

    const questionPosition2 =
      (await page.locator("#questionPosition").textContent())?.trim() || "";
    result.afterSubmit = { questionPosition: questionPosition2 };
    result.checks.submitAutoAdvances = questionPosition2 === "Question 2 of 20";

    await page.goto(`${FRONTEND}/history.html`, { waitUntil: "networkidle" });
    await page.waitForSelector("#historyBody");
    const rowTexts = await page.locator("#historyBody tr").allTextContents();
    result.historyRows = rowTexts;
    const test3Row = page
      .locator("#historyBody tr", { hasText: "Test 3" })
      .first();
    result.checks.historyShowsTest3 = await test3Row.count().then((n) => n > 0);
    if (result.checks.historyShowsTest3) {
      const resumeText = ((await test3Row.textContent()) || "").trim();
      result.historyTest3Row = resumeText;
      await Promise.all([
        page.waitForURL(/qbank\.html\?session=/, { timeout: 30000 }),
        test3Row.locator("a").click(),
      ]);
      await page.waitForLoadState("networkidle");
      const resumedQuestionPosition =
        (await page.locator("#questionPosition").textContent())?.trim() || "";
      result.resumed = {
        url: page.url(),
        questionPosition: resumedQuestionPosition,
      };
      result.checks.resumeReturnsToProgress =
        resumedQuestionPosition === "Question 2 of 20";
    } else {
      result.checks.resumeReturnsToProgress = false;
    }

    await page.screenshot({
      path: path.join(outDir, "test3_qbank.png"),
      fullPage: true,
    });
    result.finalUrl = page.url();
  } catch (error) {
    result.error = { message: error.message, stack: error.stack };
    try {
      await page.screenshot({
        path: path.join(outDir, "test3_failure.png"),
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
