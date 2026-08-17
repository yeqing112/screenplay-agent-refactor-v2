const { chromium } = require("playwright");

(async () => {
  // Launch browser
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Navigate to the application
  await page.goto("http://localhost:5173");

  // Wait for the page to load
  await page.waitForTimeout(3000);

  // Take a screenshot
  await page.screenshot({ path: "D:\\Work\\Project\\screenplay-agent-refactor-v2\\artifacts\\browser-home.png" });

  console.log("Browser launched and navigated to home page");
  console.log("Screenshot saved to artifacts/browser-home.png");

  // Close browser
  await browser.close();
})();
