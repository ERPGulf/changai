# Review and upkeep

A pack is used only after a person who knows the business has reviewed it and set `status: Reviewed` with their name in `reviewed_by`.

## Review checklist

- [ ] The overview is accurate and says what the app does not do
- [ ] Every flow step matches what the code does, in order
- [ ] Every status value is listed, spelled as stored, with a correct meaning
- [ ] Groups (pending, accepted, failed) match how users speak
- [ ] Every field name exists in the app (script run, result "none")
- [ ] `never_send` reviewed field by field against every settings doctype
- [ ] Each metric gives the same number as the app's own dashboard on a test site
- [ ] Each report checked for how it reads data; `permission_reviewed` set honestly
- [ ] Each registered tool reads only and checks permissions
- [ ] Words confirmed by support staff; non-English terms by a native speaker
- [ ] Examples run on a test site and return sensible results
- [ ] `review_notes` cleared, or left with a decision recorded

## Keeping it current

| When | Do |
| --- | --- |
| You add, rename or remove a field, status value, report or metric | Update the pack in the same commit |
| You release a version | Update `source.commit`; rerun the field check |
| You add a settings field holding a secret | Add it to `never_send` before release |
| Users ask something changAI could not answer | Add a topic, metric, word or example |
| The format changes (`pack_version`) | Follow the migration note published with the new version |

Make the pack part of your release checklist. changAI compares each pack with the installed app on migrate and stops using entries that no longer match, so a stale pack leads to unanswered questions, not wrong answers.

[Previous: Drafting with an AI tool](drafting-with-ai.md) · [Contents](README.md) · [Next: Common mistakes](common-mistakes.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
