# Admin Microsoft Teams Sign-In Logic

## English

The `Sign in with Microsoft Teams` button now authorizes users directly through Microsoft Entra, not through the KBC `auth_user` table.

Current flow:

1. The user clicks `Sign in with Microsoft Teams`.
2. The user signs in with Microsoft.
3. The backend receives the Microsoft authorization callback and exchanges the code for tokens.
4. The backend calls Microsoft Graph `/me` to confirm the signed-in directory user.
5. The backend calls Microsoft Graph `/me/transitiveMemberOf/microsoft.graph.directoryRole` to check whether the user has Entra Admin Center directory-role access.
6. If the user has any allowed Entra directory/admin-center role, the system allows them into the support dashboard as `admin`.
7. If the user has `Global Administrator` or `Privileged Role Administrator`, the system treats them as `superadmin`.
8. After Entra authorization succeeds, the system syncs or creates a runtime profile in `support_accounts`.

Databases used by Teams sign-in:

- `auth_user`: no longer used to authorize Microsoft Teams admin login.
- `kbc_users_data`: not used for admin Teams login.
- `support_accounts`: used only after successful Entra authorization as the runtime dashboard profile.

The `support_accounts` runtime profile is still required for dashboard behavior such as:

- console status
- live-chat queue
- transfers
- admin sessions
- notifications

Azure requirement:

The Azure App Registration used for login must have Microsoft Graph delegated permission:

```text
Directory.Read.All
```

Admin consent must be granted for that permission. Without it, Microsoft Graph cannot read the signed-in user's Entra directory roles.

Related implementation areas:

- `backend/support_portal/services.py`
- `backend/config/settings.py`
- `backend/.env.example`

---

# Agent Support Access & Ticket Assignment Logic

## English

### Sources of Truth

There are two types of admin accounts, each with a different source of truth for support access:

**Legacy Auth accounts** (signed in via username/password from `kbc_auth_user`):
- Source of truth: Django "Support Access" group in `auth_user_groups`
- On every login, the system reads `has_support_access` from the group membership and writes it into `support_accounts.metadata["legacy_support_access"]`
- If the account is in neither "Support Access" nor "Admin Access" group, login is rejected entirely

**Entra accounts** (signed in via Microsoft Teams):
- Source of truth: `support_accounts.metadata["legacy_support_access"]`
- The Entra login sync only patches `entra_*` metadata fields — it never overwrites `legacy_support_access`
- So whatever value is set via the Manage Agents toggle persists across re-logins

### Manage Agents Toggle

The Manage Agents page (accessible only to admins with `legacyAdminAccess` or `entraDirectoryAdmin`) shows all staff accounts with a Support Access toggle.

**Toggle ON:**
- Writes `legacy_support_access = true` into `support_accounts.metadata`
- For legacy auth accounts: also adds the user to the Django "Support Access" group
- For Entra accounts: metadata only (no Django group involved)

**Toggle OFF:**
- Writes `legacy_support_access = false` into `support_accounts.metadata`
- For legacy auth accounts: also **fully removes** the user from the Django "Support Access" group
- For Entra accounts: metadata only

### Effect on Login After Toggle OFF

- **Legacy auth account toggled OFF:** Removed from Django group → next login attempt is rejected (login check requires at least one of `has_support_access` or `has_admin_access`)
- **Entra account toggled OFF:** Can still log in (Entra auth is independent), but will not receive ticket assignments

### Reactivation

The account is never deleted from `support_accounts`. Any admin with Manage Agents access can find the deactivated agent in the list (shown as "No ticket access") and toggle them back ON, which restores Django group membership and login access.

### Ticket Assignment Filter

Only agents with `legacy_support_access = true` in metadata are eligible for ticket auto-assignment:

```sql
AND (metadata->>'legacy_support_access')::boolean = TRUE
```

This applies to both quick ticket assignment and live chat assignment.

### Access Control for Manage Agents Page

The Manage Agents page is only visible to accounts that have **both**:
1. A role of `admin` or `superadmin`
2. At least one of: `legacyAdminAccess = true` OR `entraDirectoryAdmin = true`

This prevents manually created accounts (with role set to admin but no real admin authority) from accessing the page.

Related implementation areas:

- `backend/support_portal/services.py` → `update_agent_support_access`, `sync_support_staff_account_from_entra_directory_user`, `try_auto_assign_quick_ticket`, `assign_waiting_live_chat_tickets`
- `backend/support_portal/admin.py` → `sync_support_access_group_membership`
- `frontend/src/pages/support/AgentDashboard.tsx` → `toggleSupportAccess`, `canManageUsers`
- `frontend/src/lib/adminSession.ts` → `AdminSession` interface

---

## عربي

### مصادر البيانات الأساسية

في النظام نوعين من حسابات الأدمن، لكل نوع مصدر حقيقي مختلف لصلاحية الـ support access:

**حسابات Legacy Auth** (بتدخل بـ username/password من `kbc_auth_user`):
- المصدر الحقيقي: Django "Support Access" group في `auth_user_groups`
- عند كل دخول، النظام يقرأ `has_support_access` من الـ group ويكتبها في `support_accounts.metadata["legacy_support_access"]`
- لو الحساب مش في "Support Access" ولا "Admin Access" group، الدخول يترفض كليًا

**حسابات Entra** (بتدخل بـ Microsoft Teams):
- المصدر الحقيقي: `support_accounts.metadata["legacy_support_access"]`
- الـ Entra login sync بيحدّث فقط الـ `entra_*` fields — مش بيكتب فوق `legacy_support_access`
- القيمة اللي اتحطت من الـ toggle بتفضل موجودة حتى بعد الـ re-login

### تبديل الـ Manage Agents

صفحة Manage Agents (بتكون متاحة بس للأدمن اللي عنده `legacyAdminAccess` أو `entraDirectoryAdmin`) بتعرض كل الـ staff accounts مع toggle للـ Support Access.

**Toggle ON:**
- بيكتب `legacy_support_access = true` في `support_accounts.metadata`
- لحسابات legacy auth: بيضيف المستخدم لـ Django "Support Access" group
- لحسابات Entra: metadata فقط

**Toggle OFF:**
- بيكتب `legacy_support_access = false` في `support_accounts.metadata`
- لحسابات legacy auth: **بيشيل المستخدم كليًا** من Django "Support Access" group
- لحسابات Entra: metadata فقط

### تأثير الـ Toggle OFF على الدخول

- **حساب legacy auth اتعمله Toggle OFF:** اتشال من الـ group → محاولة الدخول الجاية هترفض (الدخول يحتاج `has_support_access` أو `has_admin_access`)
- **حساب Entra اتعمله Toggle OFF:** يقدر يدخل (الـ Entra auth مستقل)، بس مش هيستقبل تيكتس

### إعادة التفعيل

الحساب مش بيتمسح من `support_accounts` أبدًا. أي أدمن عنده صلاحية Manage Agents يقدر يلاقي الـ agent المعطل في القائمة (بيظهر كـ "No ticket access") ويعمله Toggle ON، وده بيرجعله عضوية الـ Django group وصلاحية الدخول.

### فلتر توزيع التيكتس

الـ agents اللي عندهم `legacy_support_access = true` في الـ metadata بس هم اللي بيتوزع عليهم التيكتس:

```sql
AND (metadata->>'legacy_support_access')::boolean = TRUE
```

ده بينطبق على توزيع التيكتس العادية والـ live chat.

### التحكم في الوصول لصفحة Manage Agents

صفحة Manage Agents بتظهر بس للحسابات اللي عندها **الاتنين**:
1. دور `admin` أو `superadmin`
2. واحدة على الأقل من: `legacyAdminAccess = true` أو `entraDirectoryAdmin = true`

ده بيمنع الحسابات اللي اتعملت يدويًا (بدور admin بس من غير صلاحية حقيقية) من الوصول للصفحة.

أماكن التنفيذ المرتبطة:

- `backend/support_portal/services.py` → `update_agent_support_access`، `sync_support_staff_account_from_entra_directory_user`، `try_auto_assign_quick_ticket`، `assign_waiting_live_chat_tickets`
- `backend/support_portal/admin.py` → `sync_support_access_group_membership`
- `frontend/src/pages/support/AgentDashboard.tsx` → `toggleSupportAccess`، `canManageUsers`
- `frontend/src/lib/adminSession.ts` → `AdminSession` interface

زر `Sign in with Microsoft Teams` أصبح يعتمد على Microsoft Entra مباشرة، وليس على جدول `auth_user` في KBC database.

منطق الدخول الحالي:

1. المستخدم يضغط `Sign in with Microsoft Teams`.
2. المستخدم يسجل دخول بحساب Microsoft.
3. الباك إند يستقبل Microsoft authorization callback ويبدل الكود بـ tokens.
4. الباك إند يستدعي Microsoft Graph `/me` للتأكد من المستخدم داخل الدليل.
5. الباك إند يستدعي Microsoft Graph `/me/transitiveMemberOf/microsoft.graph.directoryRole` لمعرفة هل المستخدم لديه أدوار إدارية في Entra Admin Center.
6. لو المستخدم لديه أي Entra directory/admin-center role مسموح، يدخل إلى support dashboard كـ `admin`.
7. لو المستخدم لديه `Global Administrator` أو `Privileged Role Administrator`، يدخل كـ `superadmin`.
8. بعد نجاح تصريح Entra، النظام يعمل sync أو create لحساب runtime داخل `support_accounts`.

قواعد البيانات المستخدمة في Teams sign-in:

- `auth_user`: لم يعد يستخدم لتصريح دخول Microsoft Teams.
- `kbc_users_data`: لا يستخدم في دخول الأدمن بتيمز.
- `support_accounts`: يستخدم فقط بعد نجاح تصريح Entra كـ runtime profile للداشبورد.

حساب `support_accounts` runtime profile ما زال مطلوبًا لتشغيل وظائف الداشبورد مثل:

- console status
- live-chat queue
- transfers
- admin sessions
- notifications

متطلب Azure:

تطبيق Azure App Registration الخاص باللوجين يجب أن يحتوي على Microsoft Graph delegated permission:

```text
Directory.Read.All
```

ويجب عمل Admin consent لهذا التصريح. بدون ذلك، Microsoft Graph لن يستطيع قراءة أدوار المستخدم الإدارية في Entra.

أماكن التنفيذ المرتبطة:

- `backend/support_portal/services.py`
- `backend/config/settings.py`
- `backend/.env.example`
