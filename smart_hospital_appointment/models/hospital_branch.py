from odoo import fields, models


class HospitalBranch(models.Model):
    _name = "hospital.branch"
    _description = "Hospital Branch"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    active = fields.Boolean(default=True)
    phone = fields.Char()
    email = fields.Char()
    address = fields.Text()

    doctor_ids = fields.Many2many(
        "hospital.doctor",
        "hospital_doctor_branch_rel",
        "branch_id",
        "doctor_id",
        string="Doctors",
    )
    patient_ids = fields.One2many("hospital.patient", "branch_id", string="Patients")
    appointment_ids = fields.One2many(
        "hospital.appointment", "branch_id", string="Appointments"
    )

    _sql_constraints = [
        ("hospital_branch_name_uniq", "unique(name)", "Branch name must be unique."),
        ("hospital_branch_code_uniq", "unique(code)", "Branch code must be unique."),
    ]
