from odoo import api, fields, models


class HospitalDoctor(models.Model):
    _name = "hospital.doctor"
    _description = "Hospital Doctor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    specialization = fields.Char(required=True)
    experience_years = fields.Integer(string="Experience (Years)", required=True)
    consultation_fee = fields.Float(required=True)
    rating = fields.Float(digits=(2, 1), default=0.0)
    is_unavailable = fields.Boolean(
        string="Unavailable", help="Enable when doctor is unavailable for appointments."
    )
    user_id = fields.Many2one("res.users", ondelete="set null")
    branch_ids = fields.Many2many(
        "hospital.branch",
        "hospital_doctor_branch_rel",
        "doctor_id",
        "branch_id",
        string="Branches",
        required=True,
    )
    availability_ids = fields.One2many(
        "hospital.doctor.availability", "doctor_id", string="Availability"
    )
    appointment_ids = fields.One2many(
        "hospital.appointment", "doctor_id", string="Appointments"
    )
    total_patients = fields.Integer(compute="_compute_metrics")
    completed_appointments = fields.Integer(compute="_compute_metrics")

    @api.depends("appointment_ids.state", "appointment_ids.patient_id")
    def _compute_metrics(self):
        for rec in self:
            completed = rec.appointment_ids.filtered(
                lambda a: a.state in ("completed", "released")
            )
            rec.completed_appointments = len(completed)
            rec.total_patients = len(completed.mapped("patient_id"))


class HospitalDoctorAvailability(models.Model):
    _name = "hospital.doctor.availability"
    _description = "Doctor Availability Slot"
    _order = "doctor_id, day_of_week, start_time"

    doctor_id = fields.Many2one("hospital.doctor", required=True, ondelete="cascade")
    branch_id = fields.Many2one("hospital.branch", required=True, ondelete="cascade")
    day_of_week = fields.Selection(
        [
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        required=True,
    )
    start_time = fields.Float(required=True, help="24h format. Example: 9.5 for 09:30")
    end_time = fields.Float(required=True, help="24h format. Example: 17.0 for 17:00")
    slot_minutes = fields.Integer(default=30, required=True)

    _sql_constraints = [
        ("doctor_slot_minutes_positive", "CHECK(slot_minutes > 0)", "Slot minutes must be positive."),
        ("doctor_slot_time_valid", "CHECK(end_time > start_time)", "End time must be greater than start time."),
    ]
