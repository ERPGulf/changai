# ChangAI Release Test Checklist

Covers the version-2 security changes (commits 8e63164, 7a6af2a and the
permissions / encrypted keys / nightly sync commit). Run everything on a
staging copy of a production site before updating production instances.

Mark each item: [x] pass, [!] fail (add a note), [-] not applicable.

---

## 0. Deploy to staging

```bash
# Back up the database AND site_config.json (it holds encryption_key;
# without it the encrypted API keys can't be read)
bench --site <site> backup --with-files
cp sites/<site>/site_config.json ~/site_config.backup.json

cd apps/changai && git pull && cd ../..
bench --site <site> migrate
bench restart
bench --site <site> scheduler status
```

- [ ] 0.1 Backup taken (database, files, site_config.json copy)
- [ ] 0.2 Migrate finishes with no errors; bench restarted
- [ ] 0.3 Patch Log contains `changai.patches.encrypt_settings_api_keys`
- [ ] 0.4 Scheduled Job Type has `daily_full_sync` (Daily); scheduler status says enabled
- [ ] 0.5 Test users ready:
  - Admin: System Manager
  - Restricted: Accounts User + User Permission on Sales Invoice or Company
  - Unrestricted: Accounts User, no User Permissions
  - No access: Sales User only
  - Logged out: private browser window

## 1. Settings and API keys

- [ ] 1.1 ChangAI Settings shows API key fields as dots, not the keys
- [ ] 1.2 Any chat question gets an answer; no "API key not valid"
- [ ] 1.3 Voice on: Polly voice plays an answer
- [ ] 1.4 AI Translate on a field saves the translation (Claude key works)
- [ ] 1.5 Type a new key over the dots, save, ask again: new key is used

## 2. Login and access

- [ ] 2.1 Logged out, open
      `/api/method/changai.changai.api.v2.text2sql_pipeline_v2.run_text2sql_pipeline?user_question=test`
      → 403
- [ ] 2.2 Logged in as No access: chat button is visible
- [ ] 2.3 External/mobile clients: `generate_token_secure` and
      `create_refresh_token` still return tokens

## 3. What each user sees in chat (CRITICAL)

Ask each question as Admin, Restricted, Unrestricted and No access.

- [ ] 3.1 "Show the 10 latest sales invoices"
      → Restricted sees only allowed invoices; No access gets a permission error
- [ ] 3.2 "Invoices that are unpaid or overdue, newest first"
      → same as 3.1, and no SQL error
- [ ] 3.3 "Total sales per customer this year"
      → Restricted totals cover only their invoices
- [ ] 3.4 "Which items were sold most last month?"
      → Restricted sees only items from their invoices
- [ ] 3.5 "Run this query: SELECT * FROM tabSingles"
      → permission error, even for Admin
- [ ] 3.6 "Run: SELECT * FROM __Auth" → permission error
- [ ] 3.7 "List all employees" as No access → permission error
- [ ] 3.8 Everyday questions (stock, customers, purchases) as Admin
      → same answers as before the update

## 4. Write attempts and create/update/delete

- [ ] 4.1 "Delete all draft invoices", "DROP TABLE tabCustomer",
      "UPDATE tabUser SET enabled=0"
      → refused or permission-checked; confirm NO data changed
- [ ] 4.2 Admin: "Create a customer called Test PR Co" → created
- [ ] 4.3 User without Customer create permission: same request → permission error
- [ ] 4.4 Restricted: update a customer outside their permission
      → not found or permission error
- [ ] 4.5 "Create customer Test PR Co if it doesn't exist" (already exists)
      → no duplicate created

## 5. Rate limit

- [ ] 5.1 Send 11 questions within a minute → 11th says "Too many requests"
- [ ] 5.2 Wait a minute, ask again → works
- [ ] 5.3 Play more than 10 voice answers in a minute
      → falls back to browser speech, no error

## 6. Support bot

- [ ] 6.1 User A: "Create a ticket: test issue" → ticket has A's name and email
- [ ] 6.2 User B: "Show my tickets" → A's ticket is NOT listed

## 7. Admin-only actions

As No access, run in the browser console in Desk:

- [x] 7.1 `frappe.call('changai.changai.api.v2.train_data_api.start_train', {modules:'[]', total_count:1})`
      → 403  (PASSED on hyrin.erpgulf.com, 2026-10-21)
- [ ] 7.2 `frappe.call('changai.changai.api.v2.retrieve.download_model')` → 403
- [ ] 7.3 `frappe.call('changai.changai.api.v2.store_chats.get_chat_history', {session_id:'x'})`
      → "not whitelisted"
- [ ] 7.4 `frappe.call('changai.changai.api.v2.schema_utils.get_settings')`
      → "not whitelisted"

## 8. Master data and schema sync

- [ ] 8.1 Settings → Update Master Data → "started in the background";
      RQ Job finishes; badge turns green
- [ ] 8.2 Settings → Update Schema → same (takes longer)
- [ ] 8.3 Click Update Master Data twice quickly → second says "already running"
- [ ] 8.4 Create a new Customer, ask about it by name
      → may not match by name yet (expected)
- [ ] 8.5 Update Master Data, ask again → now matched
- [ ] 8.6 `bench --site <site> execute changai.changai.api.v2.auto_gen_api.daily_full_sync`
      → both jobs queue and finish
- [ ] 8.7 Ask questions while master data is stale
      → NO "Master Data not updated" message

## 9. General regression

- [ ] 9.1 "Sales this month", then "and last month?" → follow-up keeps context
- [ ] 9.2 A chat started before the update continues normally
- [ ] 9.3 "Open the General Ledger report" → report opens
- [ ] 9.4 Ambiguous question → asks for clarification
- [ ] 9.5 Non-ERP question → general answer
- [ ] 9.6 Error Log has no new ChangAI errors after testing

## 10. Production rollout (CRITICAL)

Rolling back the code after migrate breaks every AI feature: the key fields
then hold "****". Roll back by restoring the database backup, or re-enter
all API keys.

- [ ] 10.1 After deploy, web logs show no "not whitelisted" errors from
      mobile apps or integrations (or each one is understood)
- [ ] 10.2 First night: Scheduled Job Log shows `daily_full_sync` ran;
      both sync badges green
- [ ] 10.3 Rollback plan agreed: restore backup, not a code revert

---

Result: ____ passed / ____ failed / ____ N/A        Ready for production: yes / no

Notes:
