// Copyright (c) 2026, ERPGulf and contributors
// For license information, please see license.txt
frappe.ui.form.on("ChangAI Settings", {
    refresh: async function (frm) {
        const schema_wrapper = frm.fields_dict.update_schema_file.$wrapper;
        const master_wrapper = frm.fields_dict.update_masterdata_file.$wrapper;
        setup_badge_wrapper(master_wrapper);
        setup_badge_wrapper(schema_wrapper);
        const [
            master_status,
            schema_status
        ] = await Promise.all([
            check_updates("master_data.yaml"),
            check_updates("schema.yaml")
        ]);
        add_or_update_badge(master_wrapper, master_status.badge_class, master_status.badge_text);
        add_or_update_badge(schema_wrapper, schema_status.badge_class, schema_status.badge_text);

        async function applyTooltips(context, fieldsWithTooltips) {
            fieldsWithTooltips.forEach((field) => {
                let fieldContainer;
                if (context.fields_dict?.[field.fieldname]) {
                    fieldContainer = context.fields_dict[field.fieldname];
                }
                else if (context.dialog?.fields_dict?.[field.fieldname]) {
                    fieldContainer = context.dialog.fields_dict[field.fieldname];
                }
                else if (context.page) {
                    fieldContainer = $(context.page).find(`[data-fieldname="${field.fieldname}"]`).closest('.frappe-control');
                }
                if (!fieldContainer) {
                    console.error(`Field '${field.fieldname}' not found in the provided context.`);
                    return;
                }
                const fieldWrapper = fieldContainer.$wrapper || $(fieldContainer);
                if (!fieldWrapper || fieldWrapper.length === 0) {
                    console.error(`Field wrapper for '${field.fieldname}' not found.`);
                    return;
                }

                if (fieldWrapper.find('.tooltip-container').length > 0) {
                    return;
                }

                let labelElement;
                const buttonElement = fieldWrapper.find('button').first();
                const isButtonField = (fieldContainer.df && fieldContainer.df.fieldtype === 'Button')
                    || buttonElement.length > 0;

                // For button fields, anchor tooltip next to the actual button text.
                if (isButtonField && buttonElement.length > 0) {
                    labelElement = buttonElement;
                }

                // 1. Try label
                else if (fieldWrapper.find('label').length > 0) {
                    labelElement = fieldWrapper.find('label').first();
                }
                // 2. Try control-label
                else if (fieldWrapper.find('.control-label').length > 0) {
                    labelElement = fieldWrapper.find('.control-label').first();
                }
                else if (context.dialog || context.page) {
                    labelElement = fieldWrapper.find('.form-control').first();
                }

                if (!labelElement || labelElement.length === 0) {
                    console.error(`Label for field '${field.fieldname}' not found.`);
                    return;
                }

                const tooltip = new ChangAITooltip({
                    containerClass: "tooltip-container",
                    tooltipClass: "custom-tooltip",
                    iconClass: "info-icon",
                    text: field.text,
                    links: field.links || [],
                });
                tooltip.renderTooltip(labelElement[0]);
            });
        }
        const fieldsWithTooltips = [
            {
                fieldname: "remote",
                text: `Use a remote AI server instead of the local server.`,
            },
            {
                fieldname: "from_language",
                text: `Default source language used for AI translation.`,
            },
            {
                fieldname: "to_language",
                text: `Default target language used for AI translation.`,
            },
            {
                fieldname: "gemini_api_key",
                text: `Gemini API key from Google AI Studio (Free Tier).`,
            },
            {
                fieldname: "retain_memory",
                text: `Allows the AI to remember previous conversation context.`,
            },
            {
                fieldname: "gemini_location",
                text: `Google Cloud region for Gemini Paid Tier. Example: us-central1.`,
            },
            {
                fieldname: "gemini_project_id",
                text: `Google Cloud Project ID for Gemini Paid Tier.`,
            },
            {
                fieldname: "gemini_json_content",
                text: `Google Cloud Service Account JSON credentials.`,
            },
            {
                fieldname: "llm",
                text: `Select the AI model used for SQL generation and responses.`,
            },
            {
                fieldname: "result_formatting",
                text: `"Model" gives AI-formatted responses. "Local" uses simple code-based formatting.`,
            },
            {
                fieldname: "update_masterdata_file",
                text: `
            <b>Last updated:</b>
            <span style="color:#ffd43b;font-weight:700;">
            ${master_status.formatted_date}
            </span><br><br>

            Updates the business master data used by ChangAI.<br>
            Run this when important records change.
        `,
            },
            {
                fieldname: "choose_file_size",
                text: `Number of records used for training data generation.`,
            },
            {
                fieldname: "update_schema_file",
                text: `
            <b>Last updated:</b>
            <span style="color:#ffd43b;font-weight:700;">
                ${schema_status.formatted_date}
            </span><br><br>

            Updates the latest ERPNext schema and fields for ChangAI.
        `,
            },
            {
                fieldname: "openai_api_key",
                text: `OpenAI API key for training and fallback AI tasks.`,
            },
            {
                fieldname: "claude_api_key",
                text: `Claude API key for schema enrichment and data generation.`,
            },
            {
                fieldname: "tts_provider",
                text: "Choose the Text-to-Speech provider. Use Polly for high-quality AI voices with AWS Polly credentials; otherwise browser speech is used automatically"
                ,
            },
            {
                fieldname: "module_and_description",
                text: "Add modules with their descriptions, select them from the table, then click Create Train Data to generate the training dataset.",
            }


        ];
        applyTooltips(frm, fieldsWithTooltips);
        frm.add_custom_button(__('Download Embedding Model'), () => {
            frappe.call({
                method: "changai.changai.api.v2.retrieve.download_model",
                freeze: true,
                freeze_message: "Downloading Model...",
                callback(r) {
                    if (!r.message) return;
                    frappe.show_alert({
                        message: __("Model download started in the background. This may take a few minutes."),
                        indicator: "blue"
                    }, 8);
                },
                error(r) {
                    frappe.msgprint({
                        title: __("Error"),
                        message: __("Failed to start model download. Please try again."),
                        indicator: "red"
                    });
                }
            });
        });
    },
    update_masterdata_file(frm) {
        frappe.call({
            method: "changai.changai.api.v2.auto_gen_api.update_masterdata",
            freeze: true,
            freeze_message: "Updating Master Data...",
            callback(r) {
                console.log(r.message);
            }
        });
    },

    update_schema_file(frm) {
        frappe.call({
            method: "changai.changai.api.v2.auto_gen_api.sync_schema_and_enqueue_descriptions",
            freeze: true,
            freeze_message: "Syncing schema...",
            callback(r) {
                console.log(r.message);
            }
        });
    },

    create_train_data(frm) {
        create_data_from_selected_rows(frm);
    }
});


function create_data_from_selected_rows(frm) {
    const table_field = "module_and_description";
    const grid = frm.fields_dict[table_field].grid;
    const selected_rows = grid.get_selected_children();

    if (!selected_rows.length) {
        frappe.msgprint({
            title: __("No modules selected"),
            message: __("Please select at least one row."),
            indicator: "orange"
        });
        return;
    }

    const modules = selected_rows.map(row => ({
        module: row.module,
        description: row.description || ""
    }));

    frappe.call({
        method: "changai.changai.api.v2.train_data_api.start_train",
        args: {
            modules: modules,
            module_name: frm.doc.choose_module,
            total_count: frm.doc.choose_file_size
        },
        freeze: true,
        freeze_message: "Creating Data...",
        callback(r) {
            console.log("Response:", r.message);
        }
    });
}

function setup_badge_wrapper(wrapper) {
    wrapper.css({
        display: "inline-flex",
        alignItems: "center",
        gap: "10px"
    });
}

function add_or_update_badge(wrapper, badge_class, badge_text) {
    wrapper.find(".changai-sync-badge").remove();

    wrapper.find("button").after(`
        <span class="changai-sync-badge ${badge_class}">
            ${badge_text}
        </span>
    `);
}

async function check_updates(file_name) {

    const r = await frappe.call({
        method: "changai.changai.api.v2.schema_utils.check_file_updates",
        args: {
            file_name: file_name
        }
    });
    const is_stale = r.message?.is_stale;
    const data = r.message?.data;
    const last_sync = r.message?.last_sync;
    const date = new Date(last_sync);  // no " UTC" suffix
    const formatted_date = date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
    });
    let badge_class = "badge-yellow";
    let badge_text = "Unknown";


    if (is_stale === true) {
        badge_class = "badge-yellow";
        badge_text = `${formatted_date}`
    }

    if (is_stale === false) {
        if (data) {
            badge_class = "badge-green";
            badge_text = `${formatted_date}`
        }
        else {
            badge_class = "badge-red";
            badge_text = "Not updated yet"
        }
    }
    return {
        badge_class,
        badge_text,
        formatted_date
    }
}
