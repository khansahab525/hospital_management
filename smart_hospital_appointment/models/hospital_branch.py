from odoo import api, fields, models


class HospitalBranch(models.Model):
    _name = "hospital.branch"
    _description = "Hospital Branch"
    _inherit = ["hospital.branch.filtered"]
    _hospital_branch_field = "id"
    _order = "name"

    @api.model
    def _get_hospital_branch_search_domain(self):
        user = self.env.user
        if (
            self.env.su
            or not user.allowed_branch_ids
            or not user.branch_id
            or user.has_group("base.group_system")
        ):
            return []
        return [("id", "=", user.branch_id.id)]

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
