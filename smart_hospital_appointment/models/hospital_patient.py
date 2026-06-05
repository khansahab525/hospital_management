from odoo import api, fields, models


class HospitalPatient(models.Model):
    _name = "hospital.patient"
    _description = "Hospital Patient"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    patient_code = fields.Char(
        string="Patient ID", readonly=True, default=lambda self: "New", copy=False
    )
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    user_id = fields.Many2one("res.users", ondelete="set null")
    age = fields.Integer(required=True)
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("other", "Other")], required=True
    )
    phone = fields.Char(required=True)
    email = fields.Char()
    address = fields.Text()
    medical_history = fields.Html()
    allergies = fields.Text()
    branch_id = fields.Many2one("hospital.branch", required=True, tracking=True)
    appointment_ids = fields.One2many(
        "hospital.appointment", "patient_id", string="Appointments"
    )
    appointment_count = fields.Integer(compute="_compute_appointment_count")

    _sql_constraints = [
        ("hospital_patient_code_uniq", "unique(patient_code)", "Patient ID must be unique."),
    ]

    @api.depends("appointment_ids")
    def _compute_appointment_count(self):
        for rec in self:
            rec.appointment_count = len(rec.appointment_ids)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("patient_code", "New") == "New":
                vals["patient_code"] = seq.next_by_code("hospital.patient") or "New"
        return super().create(vals_list)
