#!/usr/bin/env node
// Copyright 2026 Ilya Sherman (ishermandom@)
// SPDX-License-Identifier: MIT

// Drives the convention-card-maker Streamlit app in a headless browser:
// upload a card PDF, fill in reminders, generate, download, and check for
// console errors. Consolidates the ad-hoc verification scripts written
// repeatedly during development into one reusable driver.
//
// One-time setup: `npm install` (installs playwright-core).
//
// Usage:
//   node verify_ui.mjs <app-url> <card-pdf-path> [chrome-executable-path]
//
// Example (local dev server):
//   node verify_ui.mjs http://localhost:8501 \
//     ../bridge-private/convention_cards/virginia/bridgewinners.pdf
//
// Example (live deployment):
//   node verify_ui.mjs https://ruffdraft.onrender.com \
//     ../bridge-private/convention_cards/virginia/bridgewinners.pdf

import { chromium } from 'playwright-core';

const DEFAULT_CHROME_EXECUTABLE =
  '/Users/Shared/playwright/chromium-1217/chrome-mac-arm64/' +
  'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const SAMPLE_REMINDERS = '# Test\n- A sample reminder\n- **Bold** reminder\n';
const DOWNLOAD_PATH = '/tmp/verify_ui-download.pdf';

const [, , appUrl, cardPath, chromeExecutable] = process.argv;

if (!appUrl || !cardPath) {
  console.error(
    'Usage: node verify_ui.mjs <app-url> <card-pdf-path> [chrome-executable-path]'
  );
  process.exit(1);
}

async function main() {
  const browser = await chromium.launch({
    executablePath: chromeExecutable || DEFAULT_CHROME_EXECUTABLE,
  });
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  await page.goto(appUrl, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=Convention Card Maker', { timeout: 20000 });

  await page.locator('input[type="file"]').setInputFiles(cardPath);
  const cardFileName = cardPath.split('/').pop();
  await page.waitForSelector(`text=${cardFileName}`, { timeout: 15000 });

  await page.locator('textarea').fill(SAMPLE_REMINDERS);

  // Give the fill's WebSocket round trip time to reach the server before
  // clicking. Against localhost the round trip is near-instant and this
  // isn't needed, but against a real deployment, clicking immediately can
  // race ahead of it — Streamlit's frontend ends up re-sending the
  // textarea's value instead of ever registering the button click, so the
  // script hangs waiting for a download that never starts. A human always
  // leaves a natural gap here; scripted input doesn't unless told to.
  await page.waitForTimeout(1500);

  // A single real click both blurs+commits the textarea and registers as
  // the generate action — see the "Generate is never disabled" fix. Do NOT
  // reintroduce a disabled= condition on this button without re-testing
  // that a single click still works (Playwright's actionability check
  // hides this bug: it refuses to click a disabled element, so `.click()`
  // alone won't catch a regression here — use `.click({force: true})`
  // followed by a second `.click()` to reproduce the two-click symptom).
  await page.getByRole('button', { name: 'Generate' }).click();

  const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
  await page.waitForSelector('text=Download print-ready.pdf', {
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Download print-ready.pdf' }).click();
  const download = await downloadPromise;
  await download.saveAs(DOWNLOAD_PATH);

  await browser.close();

  console.log('CONSOLE_ERRORS:', JSON.stringify(consoleErrors));
  console.log('DOWNLOADED_TO:', DOWNLOAD_PATH);

  if (consoleErrors.length > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('DRIVER_ERROR:', err);
  process.exit(1);
});
