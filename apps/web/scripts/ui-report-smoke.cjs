const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.TENDERLENS_BROWSER_PATH ? { executablePath: process.env.TENDERLENS_BROWSER_PATH } : {}),
  });
  const out = process.env.TENDERLENS_SCREENSHOT_DIR;
  const finding = { label: 'Registered supplier', detail: 'Active NTN and GST registration are required.', page_numbers: [1] };
  const profile = { name: 'Capital Office Solutions / Demo', capabilities: 'IT equipment supply and installation',
    registrations: 'Active NTN and GST.', experience: 'Six years supplying similar equipment',
    financial_capacity: 'PKR 30 million available funds', available_documents: 'Certificates and contracts', constraints: 'Security terms need clarification' };
  const analysis = { document_id: 'demo', status: 'ready', content: {
    overview: { label: 'Office equipment procurement', detail: 'Supply, installation and support of equipment for an Islamabad office.', page_numbers: [1] },
    important_dates: [{ label: 'Submission deadline', detail: '9 June 2025 (historical)', page_numbers: [1] }],
    eligibility: [finding], mandatory_requirements: [finding], required_documents: [finding],
    financial_conditions: [], deliverables: [finding], risks: [],
  }};
  const assessment = { document_id: 'demo', status: 'ready', profile, content: { company_name: profile.name,
    recommendation: 'review_required', score: 75, coverage: 80, evaluated_on: '2026-10-06',
    summary: 'Relevant capabilities. Confirm the financial security requirements.', comparisons: [{
      requirement_id: 'eligibility:0', category: 'eligibility', label: finding.label, requirement: finding.detail,
      mandatory: true, status: 'unknown', reason: 'Supporting records need review.', profile_evidence: '',
      profile_fields: ['registrations'], entered_information: [{field:'registrations',value: profile.registrations + ' Evidence details. '.repeat(30) + ' END OF FULL ENTRY'}],
      missing_information: 'Provide identifiers and supporting records.', suggested_input: 'NTN: [identifier]; GST: [identifier].', page_numbers: [1],
    }] }};
  assessment.content.comparisons.push({ ...assessment.content.comparisons[0], requirement_id: 'eligibility:1', label: 'Second comparison' });
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [];
      let analysisReady = false;
      page.on('pageerror', error => errors.push(error.message));
      let includeCompany = null;
      await page.route('**/documents**', async route => {
        const url = new URL(route.request().url());
        let body;
        if (url.pathname === '/documents') body = [{ id:'demo',filename:'Office equipment tender.pdf',size_bytes:1024,page_count:1,status:'ready',embedding_status:'ready' }];
        else if (url.pathname.endsWith('/analysis')) body = analysisReady ? analysis : { ...analysis, status: 'not_started', content: null };
        else if (url.pathname.endsWith('/assessment')) body = assessment;
        else if (url.pathname.endsWith('/pages')) body = [{page_number:1,text:'Active NTN and GST registration are required.',char_count:44,ocr_required:false,extraction_method:'embedded',ocr_confidence:null}];
        else if (url.pathname.endsWith('/report')) {
          assert.equal(route.request().headers()['x-demo-access-code'], 'demo-code');
          includeCompany = url.searchParams.get('include_company');
          return route.fulfill({ contentType:'application/pdf', body: Buffer.from('%PDF-1.4\nTEST DOWNLOAD\n%%EOF'),headers:{'Access-Control-Allow-Origin':'*'} });
        } else return route.fallback();
        return route.fulfill({ json:body, headers:{'Access-Control-Allow-Origin':'*'} });
      });
      await page.goto(process.env.TENDERLENS_TEST_URL || 'http://localhost:3005');
      await page.getByRole('button',{name:'Office equipment tender.pdf',exact:false}).click();
      const warning = page.locator('#report .warning-notice');
      await warning.waitFor();
      assert.ok((await warning.innerText()).includes('Report download is locked'));
      assert.equal(await warning.getAttribute('role'),'status');
      assert.equal(await page.getByRole('button',{name:'↓ Download PDF report'}).isDisabled(),true);
      await warning.getByRole('link',{name:'Go to Analyze tender ↑'}).click();
      assert.equal(await page.locator('#analyze-tender').evaluate(el => el === document.activeElement),true);
      analysisReady = true;
      await page.reload();
      await page.getByRole('button',{name:'Office equipment tender.pdf',exact:false}).click();
      const downloadButton = page.getByRole('button',{name:'↓ Download PDF report'});
      await downloadButton.waitFor();
      await page.waitForFunction(() => !document.querySelector('#report button').disabled);
      assert.equal(await page.locator('#report .warning-notice').count(),0);
      assert.ok(await page.evaluate(() => !!(document.querySelector('#report').compareDocumentPosition(document.querySelector('.analysis-panel')) & Node.DOCUMENT_POSITION_FOLLOWING)), 'Report is before analysis');
      assert.ok(await page.evaluate(() => document.querySelector('.pages-panel > .section-title').nextElementSibling.id === 'report'), 'Report directly follows tender heading');
      const entries = page.locator('.entered-details');
      await entries.first().waitFor();
      assert.equal(await entries.count(), 2);
      assert.equal(await page.locator('.entered-details[open]').count(), 0, 'Entries default collapsed');
      assert.ok((await entries.first().locator('.entered-preview').innerText()).length < 180);
      assert.equal(await entries.first().locator('.entered-full').isVisible(), false);
      await entries.first().locator('summary').click();
      assert.equal(await entries.first().getAttribute('open'), '');
      assert.equal(await entries.nth(1).getAttribute('open'), null, 'Other comparison remains collapsed');
      assert.ok((await entries.first().locator('.entered-full').innerText()).includes('END OF FULL ENTRY'));
      await entries.first().locator('summary').focus();
      await page.keyboard.press('Enter');
      assert.equal(await entries.first().getAttribute('open'), null, 'Keyboard collapse works');
      await page.locator('#access-code').fill('demo-code');
      await page.locator('.report-option input').uncheck();
      const downloadEvent = page.waitForEvent('download');
      await downloadButton.click();
      const download = await downloadEvent;
      assert.equal(download.suggestedFilename(), 'tenderlens-report.pdf');
      assert.equal(includeCompany,'false');
      assert.equal(await page.locator('.bid-panel').count(),1);
      assert.equal(await page.locator('.report-panel').count(),1);
      await page.locator('.profile-editor summary').click();
      await page.locator('#profile-name').fill('Updated demo company');
      assert.equal(await page.locator('#profile-name').inputValue(),'Updated demo company');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      assert.equal(overflow,false,`No horizontal overflow at ${width}px`);
      const bg = await page.locator('.hero').evaluate(el=>getComputedStyle(el,'::before').backgroundImage);
      assert.ok(bg.includes('tender-architecture.jpg'));
      assert.equal(await page.locator('.hero').evaluate(el=>getComputedStyle(el).color),'rgb(48, 59, 52)');
      if(out) {
        fs.mkdirSync(out,{recursive:true});
        await page.screenshot({path:path.join(out,`ui-${width}.png`),fullPage:true});
        if(width===1440) await page.locator('.hero').screenshot({path:path.join(out,'hero-desktop.png')});
      }
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('PASS: report below tender heading; entries collapsed by default, independently expandable, keyboard collapsible; desktop/mobile download and editing.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
