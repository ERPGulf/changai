# Common mistakes

| Mistake | Result | Do this |
| --- | --- | --- |
| Copying field labels as descriptions ("ZATCA Status: ZATCA Status") | The AI learns nothing | Say what the value means and where it comes from |
| Listing status values from memory | A missed value gives wrong counts | Grep the code, dashboards and report filters |
| Writing a status in a different case from the stored value | Filters may miss rows | Copy the value exactly |
| Leaving out "what users call it" | Questions in everyday words fail | Fill `words` and `groups` |
| One metric with a vague name ("Sales") | The AI cannot tell net from gross | Separate, clearly named metrics |
| Marking a SQL report as reviewed without reading it | Users may see data across companies | Read the query; add filters or leave it unreviewed |
| Registering a function that writes or calls an API | Unintended changes | Only read-only functions under `tools` |
| Putting sample customer data in the pack | Data leaves with the pack | Use slots: `{customer}`, `{invoice}` |
| Describing how the code works, line by line | Long, and not what users ask | Describe meaning and outcomes |
| Writing the pack once and forgetting it | Entries stop matching the app | Update it with each release |

[Previous: Review and upkeep](review-and-upkeep.md) · [Contents](README.md) · [Next: A complete minimal pack](minimal-pack.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
