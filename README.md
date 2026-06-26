<div align="center">

<h1>chang<b>AI</b></h1>

Open-source AI assistant for ERPNext. Ask business questions in plain English and get instant answers without writing SQL.

[![MIT License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![ERPNext v14+](https://img.shields.io/badge/ERPNext-v14%20%7C%20v15%20%7C%20v16-blue.svg)](https://erpnext.com)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Ubuntu-lightgrey.svg)](https://ubuntu.com)
[![Maintained](https://img.shields.io/badge/status-actively%20maintained-brightgreen.svg)]()

[Setup Guide](https://youtu.be/fFxyAY_sVNs) · [Documentation](https://docs.claudion.com/Claudion-Docs/changaisetup) · [Report a Bug](https://github.com/ERPGulf/changAI/issues) · [Embedding Model 🤗](https://huggingface.co/hyrinmansoor/changAI-nomic-embed-text-v1.5-finetuned)

</div>


> **Note:** The current version is trained on ERPNext modules only. Like any AI model, it is still learning and handles a good range of all ERPNext queries well, but will not get everything right. Accuracy improves over time with more training data and feedback.


## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Setup Instructions](#setup-instructions)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [FAQs](#faqs)



## Key Features

1. **Natural Language Queries** — Ask business questions in plain English directly inside ERPNext. changAI understands your intent, retrieves the relevant schema, and returns a human-readable answer without requiring any SQL knowledge.

2. **RAG-Powered Schema Retrieval** — changAI uses Retrieval-Augmented Generation to identify the most relevant tables, fields, and master records from your ERPNext schema and Master Data before generating a query. In Local Mode, this retrieval runs entirely on your own server using the downloaded embedding model, keeping your schema data on-premise. This improves accuracy across complex, multi-table questions.

3. **Permission-Aware Results** — Every query is validated through Frappe's native permission layer using the match_conditions API. Users only see data they are authorized to access

4. **Flexible AI Engine Configuration** — changAI supports multiple AI backends. Local Mode using Google Gemini is the recommended configuration for all users. Gemini is available on a free tier for testing via Google AI Studio and on an enterprise Vertex AI tier for production workloads. Remote Mode using Qwen3 via Replicate exists as an option in settings but is not currently in a stable working phase and is not recommended for production use at this time.

5. **Voice Assistant via Amazon Polly** — changAI includes an optional voice output feature powered by Amazon Polly. When enabled, query results can be read aloud, making it easier to consume insights hands-free or in review sessions.

6. **Auto Schema and Master Data Updates** — changAI ships with the standard ERPNext schema pre-configured so you can start querying core modules immediately. Two dedicated buttons are available in the settings — **Auto Update Schema** automatically syncs your ERPNext schema including any customisations using an Anthropic Claude API key, and **Auto Update Master Data** keeps your master records such as customers, items, and suppliers in sync with the latest data in your ERPNext instance. Both can be run independently at any time.

7. **Debug Tab for Transparency** — A built-in debug interface lets you inspect each stage of the query pipeline, including retrieved tables, generated SQL, and intermediate outputs. This makes it easy to understand and troubleshoot how an answer was produced.

8. **Built-In Support Tab** — A dedicated support interface is included within the changAI interface for raising support queries directly from your ERPNext desk, without needing to leave the app or contact support through an external channel.

9. **Module-Wise Training Data Automation** — changAI includes tools to auto-generate training data on a per-module basis across your ERPNext setup. You can select individual modules such as Accounts, Inventory, or HR and generate targeted training data for each, allowing the model's retrieval accuracy to improve incrementally without needing to retrain everything at once.

10. **Fine-Tuned Embedding Model** — changAI uses a custom fine-tuned embedding model built on nomic-embed-text-v1.5, specifically trained on ERPNext schema and retrieval data for better semantic matching.

11. **Translation Support** — changAI supports multilingual ERP usage by translating values across all DocTypes. This allows users to interact with ERPNext in their preferred language. Users can configure their preferred language directly in ChangAI Settings.

12. **English & Arabic Language Support** - changAI supports ERP interactions in both English and Arabic, enabling users to query and manage ERP data in their preferred language while preserving master data values accurately.

13. **ERP Report Navigation & Smart Filter Detection** - changAI can identify when a user is requesting a standard ERPNext report and automatically open the appropriate report with relevant filters applied.

14. **Entity Creation from Natural Language** - changAI allows users to create ERP records directly from natural language requests. Users can create customers, suppliers, items, projects, leads, opportunities, and other ERP entities by simply describing what they need. changAI automatically opens the appropriate ERPNext form with detected values pre-filled, reducing manual data entry and improving productivity.

15. **Natural Language CUD Operations (Create, Update, Delete)** — changAI supports
    creating,reading, updating, and deleting ERP records directly from natural language requests in English or Arabic. Users can manage customers, suppliers, employees, contacts,and other ERP entities by simply describing what they need.

    Every CRUD operations passes through Frappe's native permission layer before
    execution. Users can  create,read, update, or delete records they are
    authorized to access. Unauthorized attempts return a clear error message
    without modifying any data.
    All write operations (Create, Update, Delete) are executed exclusively through
    Frappe ORM and read operations through permission-validated raw SQL.

**You can Enable or Disable ChangAI from "ChangAI Settings Doctype"**

## Tech Stack

**Backend**
** Please note new URL on github https://github.com/ERPGulf/changai**
- [Frappe Framework](https://frappeframework.com) — Full-stack Python web framework that powers ERPNext. Handles authentication, permissions, database queries, and API routing.
- Python 3.14 — Core language for all backend logic, model serving, and pipeline orchestration.
**Note** - Python 3.14 requires sudo apt-get install build-essential python3-dev before bench get-app

**AI and Machine Learning**

- **[Hugging Face](https://huggingface.co/)** — Central hub for model hosting, versioning, and distribution. Utilized for managing custom fine-tuned weights and leveraging the `transformers` library.
- [nomic-embed-text-v1.5 (fine-tuned)](https://huggingface.co/hyrinmansoor/changAI-nomic-embed-text-v1.5-finetuned) — Custom embedding model fine-tuned on ERPNext schema and retrieval datasets for semantic search.
- Google Gemini — Core query engine used for SQL generation. Available on a free tier via Google AI Studio and on an enterprise tier via Vertex AI for high-volume production environments.
- Qwen3 via Replicate (Remote Mode) — Used for both schema retrieval and SQL generation in the fully hosted pipeline.
- Anthropic Claude — Used optionally for schema enrichment. Provide a Claude API key to let changAI analyse your ERPNext customisations and update its understanding of your specific environment.
- Amazon Polly — Optional voice output engine. Converts query results to speech when the voice assistant feature is enabled.
- RAG (Retrieval-Augmented Generation) — Core approach for grounding SQL generation in relevant schema context before passing to the language model.

**Frontend**

- [Frappe Desk](https://frappeframework.com) — The ERPNext desk UI framework used to render the changAI interface. Provides the Chat, Debug, and Support tabs as native Frappe pages without requiring a separate frontend build or hosting setup.
- JavaScript — Used for client-side interactions within the Frappe Desk interface, including query submission, tab switching, and rendering pipeline debug output.

**Dataset**

- [ERP Retrieval Dataset on Hugging Face](https://huggingface.co/datasets/hyrinmansoor/ERP-retrieval-data-modernbert) — Custom dataset used for fine-tuning the embedding model on ERPNext-specific retrieval tasks.


## Setup Instructions

After installing changAI on your ERPNext site through Frappe Cloud or your bench, complete the following steps to configure and activate it.

**Step 1 — Open changAI Settings**

Search for **changAI Settings** in the ERPNext search bar and open the settings page. This is the central place where all engines, credentials, and options for changAI are configured.

**Step 2 — Configure the Query Engine (Google Gemini)**

changAI uses Google Gemini as its  engine for generating SQL from your natural language queries. Two tiers are available depending on your usage requirements.

**Free Tier (recommended for testing)**

The free tier is the fastest way to get started. Generate your API key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and enter it in the Gemini section of changAI Settings.

**Enterprise Tier — Vertex AI (recommended for production)**

For high-volume or production use, Vertex AI provides a more scalable and reliable backend. Set up your Google Cloud environment following the [Vertex AI getting started guide](https://cloud.google.com/vertex-ai/docs/start/cloud-environment), then enter the corresponding credentials in changAI Settings.

**Step 3 — Choose a  Mode**

In addition to the Gemini configuration, changAI supports a Remote Mode that offloads the full pipeline to Replicate .

**Local Mode**

Schema retrieval runs on your own server and SQL generation is handled by Gemini. This keeps your schema data on-premise and is the default recommended setup.

1. Uncheck the **Remote** toggle in changAI Settings
2. Confirm your Gemini credentials are saved from Step 2
3. Save the settings

**Remote Mode**
> **Warning:** Remote Mode is currently in an **Alpha/Non-Stable state**.

Both schema retrieval and SQL generation are handled by remote Replicate server using the Qwen3 model. This is a fully hosted pipeline with no local model dependency.

1. Check the **Remote** toggle in changAI Settings
2. Under the Remote tab, fill in the following fields:
   - Replicate API token
   - Prediction URL
   - Version IDs 
3. Save the settings
> 📺 **Full walkthrough:** [YouTube Setup Guide](https://youtu.be/fFxyAY_sVNs)  
> 📖 **Full docs:** [docs.claudion.com](https://docs.claudion.com/Claudion-Docs/changaisetup)

**Step 4 — Enable Voice Assistant (Optional)**

changAI includes an optional voice output feature powered by Amazon Polly that reads query results aloud.

To enable it, open the **Details** tab in changAI Settings and check **Enable Voice Chat**. Then enter your AWS credentials — AWS Access Key ID and AWS Secret Access Key. If you have not set up AWS credentials before, follow the [Amazon Polly getting started guide](https://docs.aws.amazon.com/polly/latest/dg/getting-started.html).

**Step 5 — Download the Embedding Model**

changAI uses a fine-tuned embedding model for semantic retrieval. This model downloads automatically the first time the app is installed. If a model update is released in a future version, you will need to re-download it manually.

To do this, open changAI Settings and click **Download Embedding Model**. Make sure your server has outbound internet access during this step. This keeps the embedding model local to your server, which also means your schema data does not leave your environment during the retrieval phase.

**Step 6 — Sync Master Data (Required)**

This step is mandatory. changAI needs to index your master tables before it can recognise specific names, records, and values in your queries. Without this sync, questions about specific customers, items, suppliers, or accounts will not return accurate results.

1. Navigate to **Training Tab** in ChangAI Settings.
2. Click **Update Master Data** to sync your master tables into the changAI index

**Step 7 — Sync Schema (Optional)**

changAI ships pre-configured with the standard ERPNext schema, so core modules work immediately after setup without any additional mapping. If your ERPNext instance has custom doctypes, custom fields, or significant workflow customisations, you can enrich the AI's understanding of your specific environment.

To do this, enter an [Anthropic Claude API key](https://console.anthropic.com/) in the Remote tab of changAI Settings, then click **Update Schema** in the Training tab. changAI will analyse your customisations and incorporate them into its schema context.

> Full video walkthrough: [youtu.be/twD-4scH-EM](https://youtu.be/twD-4scH-EM)  
> Full documentation: [docs.claudion.com](https://docs.claudion.com/Claudion-Docs/changaisetup)


## Usage

Once setup is complete, open the **changAI** interface from the ERPNext menu. The interface has three tabs.

**Chat Tab**

Type your business question in plain English and press Send. changAI will identify the relevant tables and fields in your schema, generate a SQL query, check it against your permissions, and return a plain English answer.
You do not need to know the underlying table structure or field names. changAI handles the schema lookup automatically.

**Debug Tab**

If a response looks unexpected or incorrect, switch to the Debug Tab to inspect each stage of the query pipeline. You can see which tables and fields were retrieved during the RAG step, the exact SQL query that was generated, and the raw result before it was converted to natural language. This is useful for understanding how a query was interpreted and for identifying where an issue may have occurred.

**Support Tab**

A built-in support interface is included for raising queries or feedback directly from within the app. This feature is currently a work in progress and will be expanded in future releases.


## How It Works

```
User Query
    |
    v
RAG Retrieval       Retrieves relevant tables, fields, and master records
    |               from the indexed schema using the fine-tuned embedding model
    v
SQL Generation      LLM generates a SQL query from the retrieved schema context
    |               (Gemini in Local Mode, Qwen3 via Replicate in Remote Mode)
    v
Permission Check    Query is validated through Frappe's match_conditions API
    |               to ensure results respect the user's access level
    v
Natural Language    Result is returned as a human-readable answer
    |               (optionally read aloud via Amazon Polly if voice is enabled)
```


## FAQs

**Do I need to know SQL to use changAI?**  
No. changAI is built for non-technical users. You type a question in plain English and the system handles schema lookup, query generation, and result formatting automatically.

**Which ERPNext versions are supported, Does it supports V15?**  
changAI supports ERPNext  v15, and v16 on Ubuntu with Python 3.14 or higher.
**Note** - Python 3.14 requires  build-essential python3-dev before bench get-app

**Which modules does changAI cover out of the box?**  
changAI ships pre-configured with the standard ERPNext schema, so modules like Accounts, Inventory, Purchasing, Sales, and HR work immediately after setup without any additional mapping. Custom doctypes and fields require a schema sync using an Anthropic Claude API key.

**Should I use the free Gemini tier or Vertex AI?**  
The free tier available at Google AI Studio is well suited for testing and low-volume usage. For production use with higher query volumes or stricter reliability requirements, Vertex AI is recommended.

**Should I use Local Mode or Remote Mode?**  
Use Local Mode if you want schema retrieval to stay on your own server and use Gemini for SQL generation. Use Remote Mode if you prefer a fully hosted pipeline through Replicate using Qwen3 with no local model dependency.

**Is the Voice Assistant required?**  
No. Amazon Polly voice output is entirely optional. changAI works fully as a text-based interface without it. Enable it only if you want query results read aloud.

**Is the Master Data sync mandatory?**  
Yes. The Master Data sync is required before changAI can recognise specific records in your queries, such as customer names, item codes, or supplier names. Without it, the AI will not return accurate results for queries that reference specific data.

**My answer looks wrong. What should I do?**  
Open the Debug Tab and inspect the generated SQL and the fields that were retrieved. This usually shows whether the issue is with schema retrieval or the SQL that was produced. You can also report the query, the output you received, and the debug output via the [GitHub Issues](https://github.com/ERPGulf/changAI/issues) page.

**The model returned an invalid query or an unexpected error. What should I do?**  
This can happen when the model fails to identify the correct tables or fields for a particular query. It is a known limitation that affects some queries during the current training phase and will improve as more training data is added over time. If you encounter this, open the Debug Tab, take a screenshot of the full output, and post it as a new issue on the [GitHub Issues](https://github.com/ERPGulf/changAI/issues) page. Include the original query you typed alongside the screenshot. This helps the team identify which queries need better coverage in future training runs.

**The embedding model did not download. What do I do?**  
Go to changAI Settings and click Download Embedding Model manually. Make sure your server has outbound internet access at the time of download. If you are on a restricted network, you may need to whitelist the Hugging Face domain.

**Is my ERPNext data sent to external servers?**  
No. In Local Mode, schema retrieval runs on your server and only the SQL query context is sent to Gemini for generation. In Remote Mode, schema retrieval also runs on Replicate. If you enable custom schema sync, your schema structure is sent to the Anthropic Claude API. Review your data sharing and compliance requirements before choosing a configuration.

**How do I improve accuracy over time?**  
Run the Train Data Automation feature to generate additional training data from your ERPNext modules. You can also re-sync the Master Data Schema after adding new doctypes or fields, and use the schema update feature to keep changAI aligned with any ERPNext customisations.


## Links

| | |
| Setup Walkthrough | [youtu.be/twD-4scH-EM](https://youtu.be/twD-4scH-EM) |
| Documentation | [docs.claudion.com](https://docs.claudion.com/Claudion-Docs/changaisetup) |
| Embedding Model | [huggingface.co/hyrinmansoor/changAI-nomic-embed-text-v1.5-finetuned](https://huggingface.co/hyrinmansoor/changAI-nomic-embed-text-v1.5-finetuned) |
| Dataset | [huggingface.co/datasets/hyrinmansoor/ERP-retrieval-data-modernbert](https://huggingface.co/datasets/hyrinmansoor/ERP-retrieval-data-modernbert) |
| Issues | [github.com/ERPGulf/changAI/issues](https://github.com/ERPGulf/changAI/issues) |
| Support | [support@erpgulf.com](mailto:support@erpgulf.com) |
| Website | [erpgulf.com](https://erpgulf.com) |


## Report Bugs
If you encounter any bugs, please report them on GitHub Issues https://github.com/ERPGulf/changAI/issues. Please include detailed information such as app screenshots, browser console logs to help the project maintainers reproduce and address the issue effectively.

<div align="center">

Please create issue on Github on any issues or feature requests. You can alway send email to support@erpgulf.com
MIT License · Actively maintained · Built by [ERPGulf](https://erpgulf.com)

</div>
