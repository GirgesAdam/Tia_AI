# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: final-internal-gate.spec.ts >> real member navigation, RBAC UI, inbox operation, and workspace switching
- Location: e2e\final-internal-gate.spec.ts:27:5

# Error details

```
Test timeout of 60000ms exceeded.
```

```
Error: expect(locator).toBeVisible() failed

Locator:  getByRole('button', { name: /Resolve/ })
Expected: visible
Received: undefined

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByRole('button', { name: /Resolve/ })
  - Protocol error (Runtime.callFunctionOn): Internal server error, session closed.

```

# Test source

```ts
  1  | import { expect, test, type Page } from "@playwright/test";
  2  | 
  3  | const memberEmail=process.env.TIA_E2E_MEMBER_EMAIL!;
  4  | const memberPassword=process.env.TIA_E2E_MEMBER_PASSWORD!;
  5  | const adminEmail=process.env.TIA_E2E_ADMIN_EMAIL!;
  6  | const adminPassword=process.env.TIA_E2E_ADMIN_PASSWORD!;
  7  | const primaryWorkspace=process.env.TIA_E2E_PRIMARY_WORKSPACE_ID!;
  8  | const secondaryWorkspace=process.env.TIA_E2E_SECONDARY_WORKSPACE_ID!;
  9  | 
  10 | async function login(page:Page,email:string,password:string){
  11 |   await page.goto("/login");
  12 |   await page.getByLabel("الإيميل").fill(email);
  13 |   await page.getByLabel("الباسورد").fill(password);
  14 |   await page.getByRole("button",{name:"تسجيل الدخول"}).click();
  15 |   await expect(page).toHaveURL(/\/dashboard/);
  16 | }
  17 | 
  18 | async function switchWorkspace(page:Page,workspaceId:string){
  19 |   const selector=page.locator('select[aria-label="Workspace"]');
  20 |   if(await selector.inputValue()!==workspaceId){
  21 |     await selector.selectOption(workspaceId);
  22 |     await page.getByRole("button",{name:"تبديل"}).click();
  23 |     await expect(page).toHaveURL(/\/dashboard/);
  24 |   }
  25 | }
  26 | 
  27 | test("real member navigation, RBAC UI, inbox operation, and workspace switching",async({page})=>{
  28 |   await login(page,memberEmail,memberPassword);
  29 |   await switchWorkspace(page,primaryWorkspace);
  30 |   await expect(page.locator('select[aria-label="Workspace"]')).toContainText("member");
  31 |   await expect(page.getByRole("link",{name:"الفريق"})).toHaveCount(0);
  32 | 
  33 |   await page.goto("/patients?q=FinalGate");
  34 |   await expect(page.getByText("FinalGate",{exact:false}).first()).toBeVisible();
  35 |   await page.goto("/appointments");
  36 |   await expect(page.getByText("الحجوزات",{exact:true}).first()).toBeVisible();
  37 |   await page.goto("/setup");
  38 |   await expect(page.getByText("إعداد العيادة",{exact:true}).first()).toBeVisible();
  39 |   await expect(page.getByRole("button",{name:"إضافة فرع"})).toHaveCount(0);
  40 | 
  41 |   await page.goto("/inbox");
  42 |   const gateConversation=page.getByText("FinalGate Channel",{exact:false}).first();
  43 |   await expect(gateConversation).toBeVisible();
  44 |   await gateConversation.click();
  45 |   const claim=page.getByRole("button",{name:"Claim"});
  46 |   await expect(claim).toBeVisible();
  47 |   await claim.click();
  48 |   const reply=page.getByPlaceholder("اكتب ردك للعميل...");
  49 |   await expect(reply).toBeVisible();
  50 |   await reply.fill("رد Final Internal Gate من member حقيقي");
  51 |   await page.getByRole("button",{name:"إرسال"}).click();
  52 |   const resolve=page.getByRole("button",{name:/Resolve/});
> 53 |   await expect(resolve).toBeVisible();
     |                         ^ Error: expect(locator).toBeVisible() failed
  54 |   await resolve.click();
  55 |   await expect(page.getByText("مفيش handoff نشط.")).toBeVisible();
  56 | 
  57 |   await switchWorkspace(page,secondaryWorkspace);
  58 |   await expect(page.locator('select[aria-label="Workspace"]')).toContainText("admin");
  59 |   await expect(page.getByRole("link",{name:"الفريق"})).toBeVisible();
  60 | 
  61 |   await page.goto("/setup");
  62 |   await page.locator('input[name="name"]').first().fill("E2E Final Gate Branch");
  63 |   await page.locator('input[name="code"]').first().fill("e2e-final-gate");
  64 |   await page.locator('input[name="city"]').first().fill("Cairo");
  65 |   await page.getByRole("button",{name:"إضافة فرع"}).click();
  66 |   await expect(page.getByText("E2E Final Gate Branch")).toBeVisible();
  67 | 
  68 |   await switchWorkspace(page,primaryWorkspace);
  69 |   await expect(page.locator('select[aria-label="Workspace"]')).toContainText("member");
  70 | });
  71 | 
  72 | test("admin sees setup/team/automation controls",async({page})=>{
  73 |   await login(page,adminEmail,adminPassword);
  74 |   await expect(page.getByRole("link",{name:"الفريق"})).toBeVisible();
  75 |   await page.goto("/setup");
  76 |   await expect(page.getByRole("button",{name:"إضافة فرع"})).toBeVisible();
  77 |   await page.goto("/automations");
  78 |   const ruleName=page.getByText("Final Gate 24h Reminder",{exact:false}).first();
  79 |   await expect(ruleName).toBeVisible();
  80 |   const ruleBody=ruleName.locator("xpath=ancestor::div[contains(@class,'p-5')][1]");
  81 |   const toggle=ruleBody.getByRole("button",{name:/تفعيل|إيقاف/});
  82 |   await expect(toggle).toBeVisible();
  83 |   const before=await toggle.textContent();
  84 |   await toggle.click();
  85 |   const afterToggle=ruleBody.getByRole("button",{name:/تفعيل|إيقاف/});
  86 |   await expect(afterToggle).not.toHaveText(before||"");
  87 |   await afterToggle.click();
  88 |   await expect(ruleBody.getByRole("button",{name:/تفعيل|إيقاف/})).toHaveText(before||"");
  89 | });
  90 | 
```