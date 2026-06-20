from odoo import api, fields, models


class HospitalDoctor(models.Model):
    _name = "hospital.doctor"
    _description = "Hospital Doctor"
    _inherit = ["hospital.branch.filtered", "mail.thread", "mail.activity.mixin"]
    _hospital_branch_field = "branch_ids"
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
    user_id = fields.Many2one(
        "res.users",
        string="Login User",
        ondelete="set null",
        help="Backend login linked to this doctor profile.",
    )
    registered_by_id = fields.Many2one(
        "res.users",
        string="Registered By",
        default=lambda self: self.env.uid,
        ondelete="set null",
        help="Staff user who created this doctor record.",
    )
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        user = self.env.user
        branch_id = self.env.context.get("hospital_branch_id") or user.branch_id.id
        if branch_id and "branch_ids" in fields_list and not res.get("branch_ids"):
            res["branch_ids"] = [(6, 0, [branch_id])]
        if "registered_by_id" in fields_list and not res.get("registered_by_id"):
            res["registered_by_id"] = user.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        user = self.env.user
        branch_id = self._get_current_hospital_branch_id()
        for vals in vals_list:
            if branch_id:
                vals["branch_ids"] = self._branch_ids_commands_with_branch(
                    vals.get("branch_ids"), branch_id
                )
                for command in vals.get("availability_ids") or []:
                    if command[0] == 0 and isinstance(command[2], dict):
                        command[2].setdefault("branch_id", branch_id)
            if not vals.get("registered_by_id"):
                vals["registered_by_id"] = user.id
        records = super().create(vals_list)
        records._sync_linked_user_groups()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "user_id" in vals:
            self._sync_linked_user_groups()
        return res

    def _sync_linked_user_groups(self):
        """Assign Hospital Doctor role to linked users."""
        doctor_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_doctor", raise_if_not_found=False
        )
        if not doctor_group:
            return
        role_groups = [
            self.env.ref(xmlid, raise_if_not_found=False)
            for xmlid in (
                "smart_hospital_appointment.group_hospital_receptionist",
                "smart_hospital_appointment.group_hospital_admin",
                "smart_hospital_appointment.group_hospital_staff",
            )
        ]
        role_groups = [g for g in role_groups if g]
        for rec in self.filtered("user_id"):
            user_updates = {}
            if not rec.user_id.allowed_branch_ids and rec.branch_ids:
                user_updates["allowed_branch_ids"] = [(6, 0, rec.branch_ids.ids)]
                user_updates["branch_id"] = rec.branch_ids[0].id
            group_ops = [(4, doctor_group.id)]
            for group in role_groups:
                if group in rec.user_id.groups_id:
                    group_ops.append((3, group.id))
            user_updates["groups_id"] = group_ops
            rec.user_id.sudo().with_context(skip_hospital_branch_sync=True).write(
                user_updates
            )
            rec.user_id._sync_hospital_branch_access()


class HospitalDoctorAvailability(models.Model):
    _name = "hospital.doctor.availability"
    _description = "Doctor Availability Slot"
    _inherit = ["hospital.branch.filtered"]
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
