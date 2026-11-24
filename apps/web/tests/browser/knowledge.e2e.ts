import { submitLogin } from './login-form';
import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const root=resolve('../..'), generated=resolve(root,'infra/local/.generated'),origin=process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';
const receiptFile=resolve(generated,'knowledge-browser-receipt.json');
const persistence=process.env.KNOWLEDGE_VERIFY_RECEIPT==='1';
type Value=Record<string,any>;
const digest=(v:unknown)=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
function phase(info:TestInfo,name:string){info.annotations=info.annotations.filter(a=>a.type!=='safe-phase');info.annotations.push({type:'safe-phase',description:name});console.log('BROWSER_PHASE: '+name);}
async function get(context: BrowserContext, path: string): Promise<any> {
  const r = await context.request.get(path);
  expect(r.status(), 'Authenticated owner BFF read').toBe(200);
  return r.json();
}
async function authenticate(page: Page, destination: string) {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((a: Value) => a.username === 'alice');
  if (!account?.password) throw new Error('Disposable Chat investor missing');
  await page.goto(destination);
  await page.getByRole('link', { name: 'Đăng nhập', exact: true }).click();
  await submitLogin(page, account);
  expect((await get(page.context(), '/auth/session')).authenticated).toBe(true);
  await page.goto(destination);
}
async function capture(page: Page, name: string) {
  expect(new URL(page.url()).origin).toBe(origin);
  const folder = resolve(root, 'output/playwright/sanitized');
  await mkdir(folder, { recursive: true });
  await page.locator('#main-content').screenshot({ path: resolve(folder, name + '.png'), mask: [page.locator('.account-name')] });
}
async function uiPost(page: Page, path: string, action: () => Promise<unknown>, status: number) {
  const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path);
  await action();
  const response = await pending;
  expect(response.status(), 'UI POST uses the real BFF').toBe(status);
  const request = response.request();
  expect(Boolean(request.headers()['x-csrf-token'])).toBe(true);
  expect(request.headers().authorization).toBeUndefined();
  return { value: await response.json(), body: request.postDataJSON(), key: request.headers()['idempotency-key'] };
}

test('real Knowledge lexical sources consent v2 mobile and same receipt',async({page},info)=>{
 test.skip(process.env.E2E_DISPOSABLE_STACK!=='1','Requires real disposable local stack');
 phase(info,'knowledge-login');
 await authenticate(page,'/#chat');
 const context=page.context();
 let saved:Value;
 if(persistence){
  saved=JSON.parse(await readFile(receiptFile,'utf8'));
  await page.goto(`/#chat?conversation=${saved.conversation_id}&job=${saved.jobs[0].id}`);
 }else{
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill('Kiến thức có nguồn');
  const created=await uiPost(page,'/api/v1/conversations',()=>page.getByTestId('chat-create').click(),201);
  const cid=created.value.id;
  saved={conversation_id:cid,jobs:[],messages:[]};
  await expect(page.getByLabel('Tùy chọn hội thoại')).toHaveCount(0);
  async function turn(content:string){
   await page.getByTestId('chat-input').fill(content);
   const submitted=await uiPost(page,`/api/v1/conversations/${cid}/messages`,()=>page.getByTestId('chat-send').click(),202);
   let job:Value={};
   await expect.poll(async()=>{job=await get(context,`/api/v1/jobs/chat/${submitted.value.job_id}`);return job.status;},{timeout:60000}).toBe('SUCCEEDED');
   expect(job.provider_usage).toEqual([]);
   const rows=await get(context,`/api/v1/conversations/${cid}/messages`);
   const message=rows.find((m:Value)=>m.id===job.result_message_id);
   saved.jobs.push({id:job.job_id,provider_usage:job.provider_usage});saved.messages.push({id:message.id,hash:digest(message.structured)});
   return message;
  }
  phase(info,'knowledge-sources');
  const answer=await turn('EW là gì?');
  expect(answer.structured.type).toBe('knowledge');expect(answer.structured.knowledge.status).toBe('REFERENCE');
  await page.getByRole('button', { name: 'Xem nguồn tham khảo', exact: true }).first().click();
  const sources=page.locator('.chat-knowledge-sources').first();
  await expect(sources).toHaveAttribute('open','');
  await sources.locator('summary').first().focus();await page.keyboard.press('Enter');
  await expect(sources).not.toHaveAttribute('open');
  await page.keyboard.press('Enter');
  await expect(sources).toHaveAttribute('open','');
  const link=sources.locator('a').first();expect(await link.getAttribute('href')).toMatch(/^https:\/\//);expect(await link.getAttribute('rel')).toContain('noopener');
  await capture(page,'knowledge-desktop');
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByTestId('chat-input')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await capture(page,'knowledge-mobile');
  await page.getByRole('button', { name: 'Trở lại hội thoại', exact: true }).click();
  phase(info,'knowledge-developer-policy');
  const session=await get(context,'/auth/session');
  const denied=await context.request.post(`/api/v1/conversations/${cid}/preferences`,{data:{llm_consent:true},headers:{Origin:origin,'X-CSRF-Token':session.csrfToken}});
  expect(denied.status()).toBe(403);
  await expect(page.getByTestId('chat-llm-consent')).toHaveCount(0);
  const missing=await turn('zxqv987nonexistent là gì?');expect(missing.structured.knowledge.status).toBe('MISSING');
  await writeFile(receiptFile,JSON.stringify(saved,null,2),{mode:0o600});
 }
 phase(info,persistence?'knowledge-persistence':'knowledge-reload');
 const rows=await get(context,`/api/v1/conversations/${saved.conversation_id}/messages`);
 for(const old of saved.messages){expect(digest(rows.find((m:Value)=>m.id===old.id).structured)).toBe(old.hash);}
 for(const old of saved.jobs){expect((await get(context,`/api/v1/jobs/chat/${old.id}`)).provider_usage).toEqual(old.provider_usage);}
 await page.reload();await expect(page.getByTestId('chat-input')).toBeVisible();
 await expect(page.getByTestId('chat-llm-consent')).toHaveCount(0);
 if(persistence){
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button', { name: 'Xem nguồn tham khảo', exact: true }).first().click();
  await page.locator('.chat-knowledge-sources > summary').first().scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const metrics=await page.locator('.chat-knowledge .muted').first().evaluate(element=>{
   const rgb=(value:string)=>(value.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
   const lum=(values:number[])=>values.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
   let node:Element|null=element,background='rgb(255,255,255)';
   while(node){const color=getComputedStyle(node).backgroundColor;if(color!=='rgba(0, 0, 0, 0)'&&color!=='transparent'){background=color;break;}node=node.parentElement;}
   const foreground=getComputedStyle(element).color,a=lum(rgb(foreground)),b=lum(rgb(background));return {foreground,background,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05),font:getComputedStyle(element).fontFamily};
  });
  expect(metrics.contrast).toBeGreaterThanOrEqual(4.5);
  await writeFile(resolve(root,'output/knowledge-rag/ui-render-metrics.json'),JSON.stringify(metrics,null,2));
  await capture(page,'knowledge-mobile-sources-persisted');
 }
 phase(info,'knowledge-complete');
});

test('real Knowledge canonical sources and explicit target accept',async({page},info)=>{
 test.skip(process.env.E2E_DISPOSABLE_STACK!=='1','Requires real disposable local stack');
 const canonicalFile=resolve(generated,'knowledge-canonical-browser-receipt.json');
 if(persistence){
  let saved:Value;
  try { saved=JSON.parse(await readFile(canonicalFile,'utf8')); }
  catch(cause) { if((cause as NodeJS.ErrnoException).code!=='ENOENT') throw cause; saved=JSON.parse(await readFile(receiptFile,'utf8')).canonical; }
  test.skip(!saved,'Requires original canonical receipt');
  await authenticate(page,`/#chat?conversation=${saved.conversation_id}`);
  const facts=await get(page.context(),`/api/v1/recommendations/${saved.recommendation_id}`);
  expect(digest(facts)).toBe(saved.facts_hash);
  const dashboard=await get(page.context(),`/api/v1/portfolios/${facts.portfolio_id}/dashboard`);
  expect(dashboard.accepted_target.id).toBe(saved.target_id);
  expect(digest(dashboard.accepted_target.allocation)).toBe(saved.target_hash);
 }else{
  const baseline=JSON.parse(await readFile(resolve(generated,'chat-api-receipt.json'),'utf8'));
  await authenticate(page,'/#chat');
  const context=page.context(),session=await get(context,'/auth/session');
  const source=await get(context,`/api/v1/portfolios/${baseline.portfolio_id}`),sourceHash=digest(source);
  const onboarded=await context.request.post('/api/v1/onboarding/portfolios',{data:{name:`Knowledge browser ${Date.now()}`,capital_vnd:'100000000',universe_id:source.universe_id,answers:{questionnaire_version:'risk-v1',horizon_months:60,liquidity_need:'low',loss_tolerance:'high',experience:'experienced'}},headers:{Origin:origin,'X-CSRF-Token':session.csrfToken}});
  expect(onboarded.status()).toBe(201);const pid=(await onboarded.json()).id;
  expect(pid).not.toBe(baseline.portfolio_id);
  await page.goto(`/#chat?portfolio=${pid}`);
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill(`Kiến thức và phân bổ ${Date.now()}`);
  const created=await uiPost(page,'/api/v1/conversations',()=>page.getByTestId('chat-create').click(),201);const cid=created.value.id,path=`/api/v1/conversations/${cid}/messages`;
  async function terminal(jid:string){let j:Value={};await expect.poll(async()=>{j=await get(context,`/api/v1/jobs/chat/${jid}`);return ['SUCCEEDED','WAITING_INPUT','FAILED'].includes(j.status);},{timeout:90000}).toBe(true);expect(j.provider_usage).toEqual([]);return j;}
  await page.getByTestId('chat-input').fill('Tạo đề xuất phân bổ');
  const first=await uiPost(page,path,()=>page.getByTestId('chat-send').click(),202);expect((await terminal(first.value.job_id)).status).toBe('WAITING_INPUT');
  expect((await get(context,`/api/v1/portfolios/${pid}/recommendations`)).length).toBe(0);
  const confirmed=await uiPost(page,path,()=>page.getByTestId('chat-confirm').last().click(),202);const result=await terminal(confirmed.value.job_id);expect(result.status).toBe('SUCCEEDED');
  const facts=await get(context,`/api/v1/recommendations/${result.recommendation_id}`);expect(facts.inputs_provenance.data_origin).toBe('real');
  await page.getByRole('button',{name:'Tài sản 0% được hiểu thế nào?',exact:true}).last().click();
  const explained=await uiPost(page,path,()=>page.getByTestId('chat-send').click(),202);expect(explained.body.recommendation_id).toBe(facts.id);expect((await terminal(explained.value.job_id)).status).toBe('SUCCEEDED');
  const rows=await get(context,path);const card=rows.find((m:Value)=>m.id===(result.result_message_id)).structured;expect(card.facts).toEqual(facts);
  await page.getByTestId('chat-result').last().getByRole('button',{name:'Xem dữ kiện và nguồn'}).click();
  const references=page.locator('.chat-detail-panel .chat-knowledge-sources');await references.locator('summary').first().click();await expect(references.locator('a').first()).toBeVisible();
  await capture(page,'knowledge-canonical-sources');
  await page.locator('.chat-detail-panel').getByTestId('chat-open-recommendation').click();await expect(page.getByTestId('accept-proposal')).toBeEnabled();
  const accepted=await uiPost(page,`/api/v1/recommendations/${facts.id}/accept`,()=>page.getByTestId('accept-proposal').click(),200);
  expect(digest(await get(context,`/api/v1/portfolios/${baseline.portfolio_id}`))).toBe(sourceHash);
  await writeFile(canonicalFile,JSON.stringify({conversation_id:cid,recommendation_id:facts.id,target_id:accepted.value.id,facts_hash:digest(facts),target_hash:digest(accepted.value.allocation)},null,2),{mode:0o600});
 }
 phase(info,'knowledge-canonical-complete');
});

test('provider controls stay developer-managed after reload',async({page},info)=>{
 test.skip(process.env.E2E_DISPOSABLE_STACK!=='1','Requires the existing local stack');
 const saved=JSON.parse(await readFile(receiptFile,'utf8'));
 await authenticate(page,`/#chat?conversation=${saved.conversation_id}`);
 await page.reload();
 await expect(page.getByTestId('chat-input')).toBeVisible();
 await expect(page.getByTestId('chat-llm-consent')).toHaveCount(0);
 await expect(page.getByText('Dữ liệu gửi tới OpenAI',{exact:true})).toHaveCount(0);
 phase(info,'knowledge-developer-policy-complete');
});

test('real RAG definition, follow-up and abstention retain their own citations', async ({ page }) => {
  const mode = process.env.RAG_V3_BROWSER_MODE;
  test.skip(!mode, 'Requires the isolated provider-off RAG acceptance stack');
  expect(['exercise', 'verify']).toContain(mode);
  expect(origin).toBe('http://127.0.0.1:3138');
  const stage = process.env.RAG_BROWSER_SUITE ?? 'v3';
  expect(['v3', 'v4', 'v5']).toContain(stage);
  const file = resolve(root, 'output/rag-quality-' + stage + '/browser-receipt.json');
  await authenticate(page, '/#chat');
  const context = page.context();
  if (mode === 'verify') {
    const saved = JSON.parse(await readFile(file, 'utf8'));
    const path = '/api/v1/conversations/' + saved.cid + '/messages';
    expect(digest(await get(context, path))).toBe(saved.messages_hash);
    await page.goto('/#chat?conversation=' + saved.cid);
    await expect(page.locator('[data-message-id="' + saved.last + '"]')).toContainText('Chưa có nguồn');
    return;
  }
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, path = '/api/v1/conversations/' + cid + '/messages';
  const cases = [
    ['EW là gì?', 'ew-definition'],
    ['Vậy nó có nhược điểm gì?', 'ew-limit'],
    ['Cơ chế phân rã hạt nhân là gì?', null],
  ] as const;
  let last = '';
  for (const [question, expected] of cases) {
    await page.getByTestId('chat-input').fill(question);
    const sent = await uiPost(page, path, () => page.getByTestId('chat-send').click(), 202);
    let job: Value = {};
    await expect.poll(async () => {
      job = await get(context, sent.value.status_url);
      return job.status;
    }).toBe('SUCCEEDED');
    expect(job.provider_usage).toEqual([]);
    const messages = await get(context, path);
    const answer = messages.find((m: Value) => m.id === job.result_message_id);
    last = answer.id;
    const visible = page.locator('[data-message-id="' + last + '"]');
    await expect(visible).toContainText(answer.content);
    const citations = answer.structured.knowledge.citations;
    if (expected) {
      expect(citations.map((p: Value) => p.claim_id)).toEqual([expected]);
      expect(answer.content).toContain(citations[0].text);
      expect(createHash('sha256').update(citations[0].text).digest('hex')).toBe(citations[0].text_hash);
      await visible.getByRole('button', { name: 'Xem nguồn tham khảo' }).click();
      await expect(page.locator('.chat-knowledge-sources blockquote').last()).toHaveText(citations[0].text);
      await page.locator('.chat-detail-panel').getByRole('button', { name: 'Thu gọn' }).click();
    } else {
      expect(citations).toEqual([]);
      await expect(visible).toContainText('Chưa có nguồn');
    }
  }
  await writeFile(file, JSON.stringify({ cid, last, messages_hash: digest(await get(context, path)) }),
    { mode: 0o600, flag: 'wx' });
});
