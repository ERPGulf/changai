# Step 3: The never-send list

`never_send` names every field whose value must never be sent to an AI model or returned to a user by changAI. The server enforces it on every tool and every reply, so this is the one section that must be complete.

```yaml
never_send:
  Company:
    - custom_private_key
    - custom_certificate
    - custom_otp
    - custom_basic_auth_from_csid
    - custom_basic_auth_from_production
  ZATCA Multiple Setting:
    - custom_private_key
    - custom_certficate
    - custom_final_auth_csid
```

What belongs here:

| Kind | Examples |
| --- | --- |
| Keys and certificates | Private keys, public keys, certificates, CSR data |
| Credentials | Passwords, API keys, tokens, basic-auth strings, OTPs |
| Signing state | Hashes or counters used to chain or sign documents |
| Personal identifiers your client would not expect an assistant to read out | National ID, passport, bank account, salary where restricted |
| Large files | XML or PDF content: the user can open the file; the AI does not need it |

How to find them:

```bash
grep -iE "key|secret|token|password|otp|auth|cert|csr|pih" fixtures/custom_field.json
```

Then read the settings doctypes field by field. Field names are not always obvious, and a misspelled name (like `custom_certficate` above) is still a secret. Use the exact field name as stored.

If you are unsure whether a field is sensitive, list it. A field wrongly listed costs one unanswered question; a field wrongly left out is a leak.

Using a Password field type in your app is still the right thing to do. `never_send` is a second layer, and it also covers secrets that older versions stored as plain text.

[Previous: Step 2: Status values, fields and doctypes](step-2-status-fields-doctypes.md) · [Contents](README.md) · [Next: Step 4: Words, metrics and reports](step-4-words-metrics-reports.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
