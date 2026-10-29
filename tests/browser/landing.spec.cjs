const {test,expect}=require('@playwright/test');
let uid;
const headers=async p=>({'X-CSRFToken':await p.locator('meta[name="csrf-token"]').getAttribute('content')});
test.beforeEach(async({page})=>{await page.goto('/login');const r=await page.request.post('/__test/session',{headers:await headers(page),data:{}});uid=(await r.json()).user_id;});
test.afterEach(async({page})=>{if(uid)await page.request.post('/__test/cleanup',{headers:await headers(page),data:{user_id:uid}});});
test('landing remains the entry before and after login',async({page})=>{
 for(const route of ['/','/workspace']){await page.goto(route);await expect(page.locator('[data-product-landing]')).toBeVisible();await expect(page.locator('.cf-product-nav')).toBeVisible();await expect(page.locator('.cf-topnav,.cf-admin-sidebar')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:`output/landing-entry-${route==='/'?'home':'member'}-${test.info().project.name}.png`,fullPage:true,animations:'disabled'});}
 await page.locator('.cf-landing-journey a').first().click();await expect(page.locator('[data-resume-editor]')).toBeVisible();await expect(page.locator('.cf-editor-rail')).toHaveCount(0);
});
test('custom choices support pointer keyboard and dynamic controller changes',async({page})=>{
 await page.goto('/workspace');const control=page.locator('[data-select-for=theme-select] .cf-select-trigger');await expect(control).toBeVisible();await control.click();let list=page.locator('.cf-select-popover:visible');await expect(list).toHaveCount(1);await page.screenshot({path:`output/landing-dropdown-${test.info().project.name}.png`,animations:'disabled'});await list.getByRole('option',{name:'深色',exact:true}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await expect(control).toHaveText('深色');await control.focus();await page.keyboard.press('ArrowDown');await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await expect(page.locator('html')).toHaveAttribute('data-theme','light');
 await control.click();await page.keyboard.press('Escape');await expect(control).toHaveAttribute('aria-expanded','false');await expect(control).toBeFocused();
 await page.goto('/workspace?view=resume-new');await expect(page.locator('[data-select-for=resume-template-quick] .cf-select-trigger')).toContainText('经典商务');await page.evaluate(()=>{const select=document.querySelector('#resume-template-quick');select.value='technical';select.dispatchEvent(new Event('change',{bubbles:true}));});await expect(page.locator('[data-select-for=resume-template-quick] .cf-select-trigger')).toHaveText('技术项目');

});
test('custom choice works inside the create dialog and preserves form values',async({page})=>{
 await page.goto('/workspace?view=resumes');await page.locator('[data-create-resume=blank]').first().click();const dialog=page.locator('[data-create-dialog]');const choice=dialog.locator('.cf-select-trigger');await choice.click();const list=page.locator('.cf-select-popover:visible');await list.getByRole('option',{name:'技术项目',exact:true}).click();await expect(dialog.locator('[name=template]')).toHaveValue('technical');await expect(choice).toHaveText('技术项目');await page.locator('[data-create-submit]').click();await expect(page.locator('#resume-template-quick')).toHaveValue('technical');
 await page.evaluate(()=>{document.querySelector('#resume-template-quick').disabled=true;});await expect(page.locator('[data-select-for=resume-template-quick] .cf-select-trigger')).toBeDisabled();
});
