from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class HospitalAppointment(models.Model):
    _name = "hospital.appointment"
    _description = "Hospital Appointment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "appointment_datetime, is_high_priority desc, id"

    name = fields.Char(
        string="Appointment Number", default=lambda self: "New", readonly=True, copy=False
    )
    patient_id = fields.Many2one("hospital.patient", required=True, tracking=True)
    doctor_id = fields.Many2one("hospital.doctor", required=True, tracking=True)
    branch_id = fields.Many2one("hospital.branch", required=True, tracking=True)
    appointment_datetime = fields.Datetime(required=True, tracking=True)
    duration_minutes = fields.Integer(default=30, required=True)
    queue_number = fields.Integer(readonly=True, copy=False, index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )
    is_high_priority = fields.Boolean(string="High Priority", tracking=True)
    estimated_wait_minutes = fields.Integer(compute="_compute_estimated_wait")
    completion_minutes = fields.Integer(
        string="Actual Consultation Time (minutes)",
        help="Captured when appointment is completed; used to estimate waiting time.",
    )
    notes = fields.Text()
    reschedule_note = fields.Char(readonly=True)
    suggested_slot = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("hospital_appointment_number_uniq", "unique(name)", "Appointment number must be unique."),
        ("hospital_appointment_duration_positive", "CHECK(duration_minutes > 0)", "Duration must be positive."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("hospital.appointment") or "New"
        recs = super().create(vals_list)
        recs._assign_queue_number()
        return recs

    def write(self, vals):
        result = super().write(vals)
        if any(key in vals for key in ("appointment_datetime", "doctor_id", "branch_id", "is_high_priority", "state")):
            self._assign_queue_number()
        return result

    @api.constrains("doctor_id", "branch_id")
    def _check_doctor_branch_consistency(self):
        for rec in self:
            if rec.branch_id and rec.doctor_id and rec.branch_id not in rec.doctor_id.branch_ids:
                raise ValidationError(_("Doctor is not assigned to the selected branch."))

    @api.constrains("appointment_datetime", "doctor_id", "state")
    def _check_double_booking(self):
        for rec in self:
            if rec.state == "cancelled":
                continue
            overlap_domain = [
                ("id", "!=", rec.id),
                ("doctor_id", "=", rec.doctor_id.id),
                ("appointment_datetime", "=", rec.appointment_datetime),
                ("state", "!=", "cancelled"),
            ]
            if self.search_count(overlap_domain):
                raise ValidationError(_("Doctor already has an appointment at this date/time."))
            rec._check_availability_slot()

    def _check_availability_slot(self):
        for rec in self:
            appt_dt = fields.Datetime.context_timestamp(rec, rec.appointment_datetime)
            weekday = str(appt_dt.weekday())
            time_float = appt_dt.hour + appt_dt.minute / 60.0
            slots = rec.doctor_id.availability_ids.filtered(
                lambda s: s.branch_id == rec.branch_id and s.day_of_week == weekday
            )
            if not slots:
                raise ValidationError(_("Doctor has no availability configured for this branch/day."))
            valid = any(slot.start_time <= time_float < slot.end_time for slot in slots)
            if not valid:
                raise ValidationError(_("Appointment datetime is outside doctor's available time slots."))

    @api.depends("doctor_id", "branch_id", "appointment_datetime", "state", "is_high_priority")
    def _compute_estimated_wait(self):
        for rec in self:
            if not rec.appointment_datetime or rec.state in ("completed", "cancelled"):
                rec.estimated_wait_minutes = 0
                continue
            queue_domain = [
                ("doctor_id", "=", rec.doctor_id.id),
                ("branch_id", "=", rec.branch_id.id),
                ("state", "in", ["confirmed", "in_progress"]),
                ("appointment_datetime", "<=", rec.appointment_datetime),
            ]
            queued = self.search(queue_domain, order="is_high_priority desc, appointment_datetime asc, id asc")
            ahead = 0
            for appt in queued:
                if appt.id == rec.id:
                    break
                ahead += 1
            avg = rec._get_average_consultation_minutes()
            rec.estimated_wait_minutes = int(ahead * avg)

    def _get_average_consultation_minutes(self):
        self.ensure_one()
        done = self.search(
            [
                ("doctor_id", "=", self.doctor_id.id),
                ("state", "=", "completed"),
                ("completion_minutes", ">", 0),
            ],
            limit=50,
            order="id desc",
        )
        if not done:
            return 30
        return max(5, sum(done.mapped("completion_minutes")) / len(done))

    def _assign_queue_number(self):
        for rec in self:
            if rec.state in ("cancelled", "completed"):
                continue
            day_start = fields.Datetime.to_datetime(rec.appointment_datetime).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            day_end = day_start + timedelta(days=1)
            domain = [
                ("doctor_id", "=", rec.doctor_id.id),
                ("branch_id", "=", rec.branch_id.id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "in", ["confirmed", "in_progress", "draft"]),
            ]
            daily = self.search(domain, order="is_high_priority desc, appointment_datetime asc, id asc")
            for idx, appt in enumerate(daily, start=1):
                appt.queue_number = idx

    def action_confirm(self):
        for rec in self:
            if rec.doctor_id.is_unavailable:
                rec.action_suggest_reschedule()
                raise UserError(_("Doctor is marked unavailable. A next available slot was suggested."))
            rec.state = "confirmed"
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("Upcoming Appointment"),
                note=_("Appointment %s is confirmed for %s.")
                % (rec.name, fields.Datetime.to_string(rec.appointment_datetime)),
                user_id=rec.doctor_id.user_id.id or self.env.user.id,
            )
        self._assign_queue_number()

    def action_in_progress(self):
        self.write({"state": "in_progress"})
        self._assign_queue_number()

    def action_complete(self):
        for rec in self:
            rec.state = "completed"
            if not rec.completion_minutes:
                rec.completion_minutes = rec.duration_minutes
        self._assign_queue_number()

    def action_cancel(self):
        self.write({"state": "cancelled"})
        self._assign_queue_number()

    def action_set_high_priority(self):
        self.write({"is_high_priority": True})
        self._assign_queue_number()

    def action_remove_high_priority(self):
        self.write({"is_high_priority": False})
        self._assign_queue_number()

    def action_suggest_reschedule(self):
        for rec in self:
            slot = rec._find_next_available_slot()
            if not slot:
                raise UserError(_("No available future slot was found for this doctor."))
            rec.suggested_slot = slot
            rec.reschedule_note = _("Doctor unavailable. Next available slot suggested.")
        return True

    def action_apply_suggested_slot(self):
        for rec in self:
            if not rec.suggested_slot:
                raise UserError(_("No suggested slot found."))
            rec.appointment_datetime = rec.suggested_slot
            rec.suggested_slot = False
            rec.reschedule_note = _("Appointment rescheduled to suggested slot.")
        self._assign_queue_number()

    def _find_next_available_slot(self):
        self.ensure_one()
        start_dt = fields.Datetime.to_datetime(self.appointment_datetime) + timedelta(minutes=30)
        horizon = start_dt + timedelta(days=30)
        availabilities = self.doctor_id.availability_ids.filtered(lambda a: a.branch_id == self.branch_id)
        if not availabilities:
            return False

        current = start_dt
        while current <= horizon:
            weekday = str(current.weekday())
            day_slots = availabilities.filtered(lambda a: a.day_of_week == weekday).sorted("start_time")
            for slot in day_slots:
                slot_start = current.replace(
                    hour=int(slot.start_time),
                    minute=int((slot.start_time % 1) * 60),
                    second=0,
                    microsecond=0,
                )
                slot_end = current.replace(
                    hour=int(slot.end_time),
                    minute=int((slot.end_time % 1) * 60),
                    second=0,
                    microsecond=0,
                )
                check = max(current, slot_start)
                while check < slot_end:
                    clash = self.search_count(
                        [
                            ("id", "!=", self.id),
                            ("doctor_id", "=", self.doctor_id.id),
                            ("appointment_datetime", "=", fields.Datetime.to_string(check)),
                            ("state", "!=", "cancelled"),
                        ]
                    )
                    if not clash:
                        return fields.Datetime.to_string(check)
                    check += timedelta(minutes=slot.slot_minutes)
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return False

    @api.model
    def cron_resequence_queue(self):
        appointments = self.search(
            [("state", "in", ["draft", "confirmed", "in_progress"])],
            order="doctor_id, branch_id, appointment_datetime asc",
        )
        appointments._assign_queue_number()
