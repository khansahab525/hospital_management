{
    "name": "Smart Hospital Appointment System",
    "version": "17.1",
    "category": "Healthcare",
    "summary": "Smart hospital workflow with appointments and queue management",
    "description": """
Smart Hospital Appointment System
=================================

Production-ready hospital appointment management for Odoo 17:
- Patient and doctor management
- Smart booking and queueing
- Priority and emergency handling
- Auto-rescheduling support
- Multi-branch operations
- Dashboards and reports
    """,
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["base", "mail", "contacts", "web", "product", "portal", "website"],
    "data": [
        "security/ir.model.access.csv",
        "security/hospital_branch_rules.xml",
        "security/hospital_portal_rules.xml",
        "data/hospital_branch_group_cleanup.xml",
        "data/hospital_branch_rules_update.xml",
        "data/website_menu.xml",
        "data/appointment_sequence.xml",
        "data/medicine_category.xml",
        "data/queue_cron.xml",
        "report/appointment_report.xml",
        "report/medicine_prescription_report.xml",
        "views/res_users_views.xml",
        "views/branch_views.xml",
        "views/patient_views.xml",
        "views/doctor_views.xml",
        "views/appointment_views.xml",
        "views/hospital_home_content_views.xml",
        "views/menu_views.xml",
        "views/portal_templates.xml",
        "views/website_templates.xml",
        "views/website_appointment_templates.xml",
        "views/website_register_templates.xml",
        "views/website_home_templates.xml",
        "views/website_layout_templates.xml",
        "views/medicine_menus.xml",
        "wizard/appointment_report_wizard_views.xml",
    ],
    "application": True,
    "installable": True,
    "assets": {
        "web.assets_backend": [
            "smart_hospital_appointment/static/src/branch_service.js",
            "smart_hospital_appointment/static/src/switch_branch_menu/switch_branch_menu.js",
            "smart_hospital_appointment/static/src/switch_branch_menu/switch_branch_menu.xml",
        ],
        "web.assets_frontend": [
            "smart_hospital_appointment/static/src/scss/doctors_page.scss",
            "smart_hospital_appointment/static/src/scss/appointments_page.scss",
            "smart_hospital_appointment/static/src/scss/home_page.scss",
            "smart_hospital_appointment/static/src/scss/hospital_header.scss",
        ],
    },
}
