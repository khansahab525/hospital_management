{
    "name": "Smart Hospital Appointment System",
    "version": "17.0.2",
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
    "depends": ["base", "mail", "contacts", "web"],
    "data": [
        "security/hospital_security.xml",
        "security/ir.model.access.csv",
        "data/appointment_sequence.xml",
        "data/queue_cron.xml",
        "report/appointment_report.xml",
        "views/branch_views.xml",
        "views/patient_views.xml",
        "views/doctor_views.xml",
        "views/appointment_views.xml",
        "views/menu_views.xml",
        "wizard/appointment_report_wizard_views.xml",
    ],
    "application": True,
    "installable": True,
}
