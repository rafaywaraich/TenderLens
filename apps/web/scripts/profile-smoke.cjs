// Run against a local dev server with Playwright available via NODE_PATH or npm.
// Uses mocked API responses; no tender, company data or Gemini requests are sent.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.TENDERLENS_BROWSER_PATH ? { executablePath: process.env.TENDERLENS_BROWSER_PATH } : {}),
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error' && /same key|unique.*key/i.test(msg.text())) errors.push(msg.text());
    });
    const docs = ['alpha', 'beta'].map(id => ({
      id, filename: `${id}.pdf`, size_bytes: 1024, page_count: 1, status: 'ready',
      error_message: null, embedding_status: 'ready', embedding_error: null,
      created_at: '2026-10-05T00:00:00Z',
    }));
    await page.route('**/documents**', async route => {
      const path = new URL(route.request().url()).pathname;
      let body;
      if (path === '/documents') body = docs;
      else if (path.endsWith('/pages')) body = [{
        page_number: 1, text: 'Sample tender evidence.', char_count: 23,
        ocr_required: false, extraction_method: 'embedded', ocr_confidence: null,
      }];
      else if (path.endsWith('/analysis') || path.endsWith('/assessment')) {
        body = { document_id: path.split('/')[2], status: 'not_started', profile: null, content: null };
      } else return route.fallback();
      await route.fulfill({ json: body, headers: { 'Access-Control-Allow-Origin': '*' } });
    });
    await page.goto(process.env.TENDERLENS_TEST_URL || 'http://localhost:3005');
    for (let i = 0; i < 8; i++) {
      await page.getByRole('button', { name: `${i % 2 ? 'beta' : 'alpha'}.pdf`, exact: false }).click();
      await page.locator('.qa-panel').waitFor();
      assert.equal(await page.locator('.bid-panel').count(), 1, 'Company form must render once');
      assert.equal(await page.locator('.qa-panel').count(), 1, 'Q&A must render once');
      assert.equal(await page.locator('#profile-name').count(), 1, 'Input IDs must be unique');
      await page.locator('#profile-name').fill(`Demo Company ${i}`);
      await page.locator('#profile-capabilities').fill(`Electrical maintenance ${i}`);
      await page.locator('#profile-registrations').fill('PEC C6 demo registration');
      await page.locator('#profile-name').press('End');
      await page.locator('#profile-name').pressSequentially(' typed');
      assert.equal(await page.locator('#profile-name').inputValue(), `Demo Company ${i} typed`);
      assert.equal(await page.locator('#profile-capabilities').inputValue(), `Electrical maintenance ${i}`);
      await page.getByRole('button', { name: 'Save profile', exact: true }).click();
      await page.getByRole('button', { name: 'Saved in this browser', exact: true }).waitFor();
      await page.locator('#tender-question').fill('What are the requirements?');
      assert.equal(await page.locator('#tender-question').inputValue(), 'What are the requirements?');
      assert.equal(await page.locator('.page').count(), 1);
    }
    assert.deepEqual(errors, [], 'No React duplicate-key errors');
    console.log('PASS: 8 document switches; single panels/pages; editable company/Q&A fields; profile save.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
