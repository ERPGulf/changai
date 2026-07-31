app_name = "changai"
app_title = "Changai"
app_publisher = "ERpGulf"
app_description = "Changai"
app_email = "support@erpgulf.com"
app_license = "mit"

from changai import __version__ as app_version
from pathlib import Path

dist_dir = Path(__file__).resolve().parent / "public" / "dist"
dist_js_path = dist_dir / "changai-chatbot.js"
dist_css_path = dist_dir / "changai-chatbot.css"
try:
    asset_build_stamp = str(int(max(dist_js_path.stat().st_mtime, dist_css_path.stat().st_mtime)))
except FileNotFoundError:
    asset_build_stamp = app_version

ASSET_VERSION = f"?v={app_version}-{asset_build_stamp}"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "changai",
# 		"logo": "/assets/changai/logo.png",
# 		"title": "Changai",
# 		"route": "/changai",
# 		"has_permission": "changai.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/changai/css/changai.css"
# app_include_js = "/assets/changai/js/changai.js"
# Include JS globally on all pages
# Include JS globally on all pages
app_include_js = [
    f"/assets/changai/dist/changai-chatbot.js{ASSET_VERSION}",
    "/assets/changai/js/ai_translate.js",
    "/assets/changai/js/tooltip.js"
]
app_include_css = [
    f"/assets/changai/dist/changai-chatbot.css{ASSET_VERSION}",
    "/assets/changai/css/tooltip.css"
]
# In hooks.py
# app_include_css = [
#     "https://unpkg.com/leaflet.locatecontrol/dist/L.Control.Locate.min.css"
# ]
# app_include_js = [
#     "https://unpkg.com/leaflet.locatecontrol/dist/L.Control.Locate.min.js"
# ]



# include js, css files in header of web templateFriday2000
# web_include_css = "/assets/changai/css/changai.css"
# web_include_js = "/assets/changai/js/changai.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "changai/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "changai/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "changai.utils.jinja_methods",
# 	"filters": "changai.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "changai.setup.install.install_system_deps"

# after_install = "changai.changai.api.v2.install.after_install"
# after_migrate = "changai.changai.api.v2.auto_gen_api.rebuild_masterdata_after_migrate"
# Uninstallation
# ------------

# before_uninstall = "changai.uninstall.before_uninstall"
# after_uninstall = "changai.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument
# before_app_install = "changai.utils.before_app_install"
# after_app_install = "changai.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "changai.utils.before_app_uninstall"
# after_app_uninstall = "changai.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "changai.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events
master_dts_to_sync = ["Customer", "Item", "Supplier", "Warehouse", "Account"]
schema_dts_to_sync = ["DocType", "Property Setter", "Custom Field"]
master_dts_events = {
    dt: {
        "after_insert": "changai.changai.api.v2.auto_gen_api.update_masterdata",
        "on_update": "changai.changai.api.v2.auto_gen_api.update_masterdata",
        "after_delete": "changai.changai.api.v2.auto_gen_api.update_masterdata",
    }
    for dt in master_dts_to_sync
}

schema_dts_events = {
    dt: {
        "after_insert": "changai.changai.api.v2.auto_gen_api.schema_sync",
        "on_update": "changai.changai.api.v2.auto_gen_api.schema_sync",
        "after_delete": "changai.changai.api.v2.auto_gen_api.schema_sync",
    }
    for dt in schema_dts_to_sync
}

doc_events = {
    "Employee": {
        "on_update": "changai.changai.api.v2.create_qr.create_qr_code",
    },
    **master_dts_events,
    **schema_dts_events,

    # "File":{"after_insert":"changai.changai.api.v2.gdoc_ai.on_file_upload"}
# # 	"*": {
# # 		"on_update": "method",
# # 		"on_cancel": "method",
# # 		"on_trash": "method"
# # 	}
}

# also runs after bench migrate
on_session_creation = [
    "changai.changai.api.v2.retrieve.load_on_startup",
    "changai.changai.api.v2.schema_utils.reload_mapping_schema_cache"
]


# boot_session = [
#     "changai.changai.api.v2.text2sql_pipeline_v2.load_on_startup",
#     "changai.changai.api.v2.schema_utils.reload_mapping_schema_cache"
# ]


# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"changai.tasks.all"
# 	],
# 	"daily": [
# 		"changai.tasks.daily"
# 	],
# 	"hourly": [
# 		"changai.tasks.hourly"
# 	],
# 	"weekly": [
# 		"changai.tasks.weekly"
# 	],
# 	"monthly": [
# 		"changai.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "changai.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "changai.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "changai.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["changai.utils.before_request"]
# after_request = ["changai.utils.after_request"]

# Job Events
# ----------
# before_job = ["changai.utils.before_job"]
# after_job = ["changai.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"changai.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "=", "ChangAI Settings"]
        ]
    }
]
