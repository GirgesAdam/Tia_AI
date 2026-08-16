import { expect, test, type Page } from "@playwright/test";

const memberEmail=process.env.TIA_E2E_MEMBER_EMAIL!;
const memberPassword=process.env.TIA_E2E_MEMBER_PASSWORD!;
const adminEmail=process.env.TIA_E2E_ADMIN_EMAIL!;
const adminPassword=process.env.TIA_E2E_ADMIN_PASSWORD!;
const primaryWorkspace=process.env.TIA_E2E_PRIMARY_WORKSPACE_ID!;
const secondaryWorkspace=process.env.TIA_E2E_SECONDARY_WORKSPACE_ID!;

async function login(page:Page,email:string,password:string){
  await page.goto("/login");
  await page.getByLabel("الإيميل").fill(email);
  await page.getByLabel("الباسورد").fill(password);
  await page.getByRole("button",{name:"تسجيل الدخول"}).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

async function switchWorkspace(page:Page,workspaceId:string){
  const selector=page.locator('select[aria-label="Workspace"]');
  if(await selector.inputValue()!==workspaceId){
    await selector.selectOption(workspaceId);
    await page.getByRole("button",{name:"تبديل"}).click();
    await expect(page).toHaveURL(/\/dashboard/);
  }
}

test("real member navigation, RBAC UI, inbox operation, and workspace switching",async({page})=>{
  await login(page,memberEmail,memberPassword);
  await switchWorkspace(page,primaryWorkspace);
  await expect(page.locator('select[aria-label="Workspace"]')).toContainText("member");
  await expect(page.getByRole("link",{name:"الفريق"})).toHaveCount(0);

  await page.goto("/patients?q=ياسمين");
  await expect(page.getByText("ياسمين خالد",{exact:false}).first()).toBeVisible();
  await page.goto("/appointments");
  await expect(page.getByText("الحجوزات",{exact:true}).first()).toBeVisible();
  await page.goto("/setup");
  await expect(page.getByText("إعداد العيادة",{exact:true}).first()).toBeVisible();
  await expect(page.getByRole("button",{name:"إضافة فرع"})).toHaveCount(0);

  await page.goto("/inbox");
  const gateConversation=page.getByText("هند مصطفى",{exact:false}).first();
  await expect(gateConversation).toBeVisible();
  await gateConversation.click();
  const claim=page.getByRole("button",{name:"Claim"});
  await expect(claim).toBeVisible();
  await claim.click();
  const reply=page.getByPlaceholder("اكتب ردك للعميل...");
  await expect(reply).toBeVisible();
  await reply.fill("أهلاً يا هند، تم استلام طلبك وتحويله للفريق المختص.");
  await page.getByRole("button",{name:"إرسال"}).click();
  const resolve=page.getByRole("button",{name:/Resolve/});
  await expect(resolve).toBeVisible();
  await resolve.click();
  await expect(page.getByText("مفيش handoff نشط.")).toBeVisible();

  await switchWorkspace(page,secondaryWorkspace);
  await expect(page.locator('select[aria-label="Workspace"]')).toContainText("admin");
  await expect(page.getByRole("link",{name:"الفريق"})).toBeVisible();

  await page.goto("/setup");
  await page.locator('input[name="name"]').first().fill("فرع مصر الجديدة — اختبار E2E");
  await page.locator('input[name="code"]').first().fill("qa-heliopolis");
  await page.locator('input[name="city"]').first().fill("Cairo");
  await page.getByRole("button",{name:"إضافة فرع"}).click();
  await expect(page.getByText("فرع مصر الجديدة — اختبار E2E")).toBeVisible();

  await switchWorkspace(page,primaryWorkspace);
  await expect(page.locator('select[aria-label="Workspace"]')).toContainText("member");
});

test("admin sees setup/team/automation controls",async({page})=>{
  await login(page,adminEmail,adminPassword);
  await expect(page.getByRole("link",{name:"الفريق"})).toBeVisible();
  await page.goto("/setup");
  await expect(page.getByRole("button",{name:"إضافة فرع"})).toBeVisible();
  await page.goto("/automations");
  const ruleName=page.getByText("تذكير موعد قبل 24 ساعة — اختبار داخلي",{exact:false}).first();
  await expect(ruleName).toBeVisible();
  const ruleBody=ruleName.locator("xpath=ancestor::div[contains(@class,'p-5')][1]");
  const toggle=ruleBody.getByRole("button",{name:/تفعيل|إيقاف/});
  await expect(toggle).toBeVisible();
  const before=await toggle.textContent();
  await toggle.click();
  const afterToggle=ruleBody.getByRole("button",{name:/تفعيل|إيقاف/});
  await expect(afterToggle).not.toHaveText(before||"");
  await afterToggle.click();
  await expect(ruleBody.getByRole("button",{name:/تفعيل|إيقاف/})).toHaveText(before||"");
});
