from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HospitalAppointmentMedicineLine(models.Model):
    _name = "hospital.appointment.medicine.line"
    _description = "Appointment Prescribed Medicine Line"
    _inherit = ["hospital.branch.filtered"]
    _hospital_branch_field = "appointment_id.branch_id"
    _order = "appointment_id, sequence, id"

    sequence = fields.Integer(default=10)
    appointment_id = fields.Many2one(
        "hospital.appointment",
        string="Appointment",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Medicine",
        required=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    days = fields.Integer(
        string="Days to Take",
        required=True,
        default=1,
        help="Number of days the medicine should be taken.",
    )
    dosage = fields.Char(
        string="Dosage",
        help="e.g. 500 mg, 10 ml",
    )
    frequency = fields.Char(
        string="Frequency",
        help="e.g. Twice daily, every 8 hours",
    )
    route = fields.Char(
        string="Route",
        help="e.g. Oral, topical",
    )
    instructions = fields.Text(
        string="Instructions",
        help="Additional directions for the patient.",
    )

    _sql_constraints = [
        ("hospital_medicine_line_qty_positive", "CHECK(quantity > 0)", "Quantity must be positive."),
        ("hospital_medicine_line_days_positive", "CHECK(days > 0)", "Days to take must be positive."),
    ]

    @api.constrains("product_id", "appointment_id")
    def _check_product_template(self):
        for line in self:
            if not line.product_id or not line.appointment_id:
                continue
            if line.appointment_id.state == "released":
                raise ValidationError(_("Medicine lines cannot be changed after the patient is released."))
            if line.appointment_id.state != "completed":
                raise ValidationError(_("Medicine lines can only be saved on completed appointments."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            appt_id = vals.get("appointment_id")
            if not appt_id:
                raise ValidationError(_("Medicine lines must be linked to an appointment."))
            appt = self.env["hospital.appointment"].browse(appt_id)
            appt.flush_recordset(["state"])
            if appt.state == "released":
                raise ValidationError(_("Medicine lines cannot be added after the patient is released."))
            if appt.state != "completed":
                raise ValidationError(_("Medicine lines can only be added when the appointment is completed."))
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            if line.appointment_id.state == "released":
                raise ValidationError(_("Medicine lines cannot be changed after the patient is released."))
            if line.appointment_id.state != "completed":
                raise ValidationError(_("Medicine lines can only be changed when the appointment is completed."))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.appointment_id.state == "released":
                raise ValidationError(_("Medicine lines cannot be removed after the patient is released."))
            if line.appointment_id.state != "completed":
                raise ValidationError(_("Medicine lines can only be removed when the appointment is completed."))
        return super().unlink()
