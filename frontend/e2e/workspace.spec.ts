import {test,expect} from '@playwright/test';

test('investigation workflow: graph, note, model card, responsive layout',async({page})=>{
  const errors:string[]=[];page.on('pageerror',err=>errors.push(err.message));
  await page.goto('/');
  const demo=await page.getByLabel('Active dataset').locator('option').filter({hasText:'Illustrative research sandbox'}).first().getAttribute('value');
  await page.getByLabel('Active dataset').selectOption(demo!);
  await expect(page.getByRole('heading',{name:/Every transaction/})).toBeVisible();
  await expect(page.locator('.metric-value').first()).not.toHaveText('—');
  await page.screenshot({path:'../runtime/overview-desktop.png',fullPage:true});
  await page.locator('.alert-row').first().click();
  await expect(page.getByText('WHY THIS WAS FLAGGED')).toBeVisible();
  await expect(page.locator('.graph-canvas canvas').first()).toBeVisible();
  await page.screenshot({path:'../runtime/investigation-desktop.png',fullPage:true});
  await page.getByLabel('Analyst note').fill('Browser verification: source context reviewed.');
  await page.getByRole('button',{name:'Save note'}).click();
  await expect(page.locator('.notes-list')).toContainText('Browser verification: source context reviewed.');
  await page.getByLabel('Investigation status').selectOption('Reviewing');
  await expect(page.getByLabel('Investigation status')).toHaveValue('Reviewing');
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Transactions CSV'}).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
  await page.getByRole('button',{name:/Models & evaluation/}).click();
  await expect(page.getByRole('heading',{name:/Measure first/})).toBeVisible();
  await page.screenshot({path:'../runtime/models-desktop.png',fullPage:true});
  await page.getByRole('button',{name:/Datasets & analysis/}).click();
  await expect(page.getByText('ANALYSIS CONTROLS')).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>window.scrollTo(0,0));
  const dismiss=page.getByRole('button',{name:'Dismiss notification'});if(await dismiss.count())await dismiss.click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../runtime/datasets-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Toggle navigation'}).click();
  await expect(page.locator('.sidebar.open')).toBeVisible();
  expect(errors).toEqual([]);
});

test('upload, analysis job, source switching, and empty/error-free states',async({page})=>{
  const errors:string[]=[];page.on('pageerror',err=>errors.push(err.message));
  await page.goto('/');
  await page.getByRole('button',{name:/Datasets & analysis/}).click();
  const filename=`browser-fixture-${Date.now()}.csv`;
  const csv=['transaction_id,sender_account_id,receiver_account_id,timestamp_iso,amount_paid,payment_currency,amount_received,receiving_currency',
    ...Array.from({length:6},(_,i)=>`tx-${i},sender-${i},hub,2026-01-01T10:0${i}:00,100,USD,100,USD`)].join('\n');
  await page.locator('input[type=file]').setInputFiles({name:filename,mimeType:'text/csv',buffer:Buffer.from(csv)});
  await expect(page.getByLabel('Active dataset').locator('option:checked')).toContainText(filename,{timeout:30000});
  await page.getByRole('button',{name:'Run analysis'}).click();
  await expect(page.getByRole('status')).toContainText('analysis completed',{timeout:30000});
  await page.getByRole('button',{name:/Network & flows/}).click();
  await expect(page.locator('.alert-row').first()).toContainText('Fan In');
  const amlsim=page.getByLabel('Active dataset').locator('option').filter({hasText:'AMLSim 20K'}).first();
  if(await amlsim.count()){
    await page.getByLabel('Active dataset').selectOption((await amlsim.getAttribute('value'))!);
    await page.getByRole('button',{name:/Datasets & analysis/}).click();
    await expect(page.getByLabel('Window (steps)')).toHaveValue('5');
    await expect(page.getByLabel('Observed dormancy days')).toBeDisabled();
  }
  await expect(page.locator('.error-banner')).toHaveCount(0);
  expect(errors).toEqual([]);
});
