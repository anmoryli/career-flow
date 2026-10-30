const {test,expect}=require('@playwright/test');
test('warm surfaces, double focus rings and dark weight compensation',async({page})=>{
 await page.goto('/login');await page.evaluate(()=>window.cfTheme('light'));const field=page.locator('[data-ui-form=auth] [name=email]');await field.focus();
 const light=await field.evaluate(node=>{const style=getComputedStyle(node);return {weight:Number(style.fontWeight),outline:style.outlineStyle,shadow:style.boxShadow,bg:getComputedStyle(document.documentElement).backgroundColor};});
 expect(light.bg).toBe('rgb(245, 245, 243)');expect(light.outline).toBe('none');expect(light.shadow).toContain('inset');expect(light.shadow).toContain('3px');
 await page.evaluate(()=>window.cfTheme('dark'));expect(await field.evaluate(node=>Number(getComputedStyle(node).fontWeight))).toBe(light.weight-40);
 expect(await page.locator('body').evaluate(node=>getComputedStyle(node).fontVariantNumeric)).toContain('tabular-nums');expect(await page.locator('body').evaluate(node=>getComputedStyle(node).backgroundColor)).not.toBe('rgb(0, 0, 0)');
 await page.screenshot({path:`output/craft-login-${test.info().project.name}.png`,fullPage:true,animations:'disabled'});
});
test('streaming glyphs and grid folds honor reduced motion',async({page})=>{
 await page.goto('/');await page.emulateMedia({reducedMotion:'no-preference'});
 const details=page.locator('.cf-public-process-steps>details').nth(1);await details.locator('summary').click();await expect(details).toHaveAttribute('open','');expect(await details.locator('.cf-fold').evaluate(node=>getComputedStyle(node).display)).toBe('grid');
 await page.evaluate(()=>{const node=document.createElement('p');node.id='test-stream';document.querySelector('#main').append(node);window.cfStreamText(node,'真实流式文本');});
 expect(await page.locator('#test-stream .cf-stream-glyph').count()).toBeGreaterThan(0);const delays=await page.locator('#test-stream .cf-stream-glyph').evaluateAll(nodes=>nodes.map(node=>parseFloat(node.style.animationDelay)));expect(delays[1]-delays[0]).toBeCloseTo(30);
 await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>window.cfStreamText(document.querySelector('#test-stream'),'真实流式文本继续'));await expect(page.locator('#test-stream .cf-stream-glyph')).toHaveCount(0);await expect(page.locator('#test-stream')).toHaveText('真实流式文本继续');
 await details.locator('summary').click();await expect(details).not.toHaveAttribute('open','');expect(await details.locator('.cf-fold-content').evaluate(node=>node.inert)).toBeTruthy();
});
test('spring physics and clipboard confirmation reset after 2.5 seconds',async({page})=>{
 await page.goto('/');await page.emulateMedia({reducedMotion:'no-preference'});
 await page.evaluate(()=>{Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.testCopied=text;}}});const node=document.createElement('p');node.dataset.reviewCandidateText='';node.textContent='经过核对的真实正文';node.id='copy-source';document.querySelector('#main').append(node);});
 const button=page.locator('.cf-copy-button');await expect(button).toBeVisible();await button.click();await expect(button).toHaveText('✓ 已复制');expect(await page.evaluate(()=>window.testCopied)).toBe('经过核对的真实正文');await expect(button).toHaveText('复制正文',{timeout:4000});
 const motion=await page.evaluate(()=>{const node=document.querySelector('#copy-source');const a=window.cfSpring(node,'drag',0,1),b=window.cfSpring(node,'confirm',0,1);return {drag:a.effect.getKeyframes().map(frame=>Number(frame.transform.match(/\(([^p]+)/)[1])),confirm:b.effect.getKeyframes().map(frame=>Number(frame.transform.match(/\(([^)]+)/)[1]))};});expect(Math.max(...motion.drag)).toBeLessThanOrEqual(1);expect(Math.max(...motion.confirm)).toBeGreaterThan(1);
});
