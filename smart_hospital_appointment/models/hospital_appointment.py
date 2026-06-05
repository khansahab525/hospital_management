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
    patient_id = fields.Many2one("res.partner", required=True, tracking=True)
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
            ("released", "Released"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )
    is_high_priority = fields.Boolean(string="High Priority", tracking=True)
    estimated_wait_minutes = fields.Integer(compute="_compute_estimated_wait")
    expected_turn_datetime = fields.Datetime(
        string="Expected time with doctor",
        compute="_compute_expected_turn_datetime",
        help="Estimated time this patient will enter consultation, based on queue position and average visit length.",
    )
    completion_minutes = fields.Integer(
        string="Actual Consultation Time (minutes)",
        help="Captured when appointment is completed; used to estimate waiting time.",
    )
    notes = fields.Text()
    reschedule_note = fields.Char(readonly=True)
    suggested_slot = fields.Datetime(readonly=True)
    medicine_line_ids = fields.One2many(
        "hospital.appointment.medicine.line",
        "appointment_id",
        string="Prescribed Medicines",
    )
    medicine_category_id = fields.Many2one(
        "product.category",
        string="Medicine root category",
        compute="_compute_medicine_category_id",
    )
    portal_released_today_count = fields.Integer(
        string="Released visits today (same doctor & branch)",
        compute="_compute_portal_released_today_count",
    )

    @api.depends()
    def _compute_medicine_category_id(self):
        categ = self.env.ref(
            "smart_hospital_appointment.product_category_hospital_medicines",
            raise_if_not_found=False,
        )
        for rec in self:
            rec.medicine_category_id = categ

    @api.depends("doctor_id", "branch_id", "appointment_datetime")
    def _compute_portal_released_today_count(self):
        Appointment = self.env["hospital.appointment"]
        for rec in self:
            if not rec.doctor_id or not rec.branch_id or not rec.appointment_datetime:
                rec.portal_released_today_count = 0
                continue
            day_start, day_end = rec._appointment_day_bounds()
            rec.portal_released_today_count = Appointment.search_count(
                [
                    ("doctor_id", "=", rec.doctor_id.id),
                    ("branch_id", "=", rec.branch_id.id),
                    ("appointment_datetime", ">=", day_start),
                    ("appointment_datetime", "<", day_end),
                    ("state", "=", "released"),
                ]
            )

    _sql_constraints = [
        ("hospital_appointment_number_uniq", "unique(name)", "Appointment number must be unique."),
        ("hospital_appointment_duration_positive", "CHECK(duration_minutes > 0)", "Duration must be positive."),
    ]

    def _get_report_base_filename(self):
        self.ensure_one()
        return self.name or _("Appointment")

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"].sudo()
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("hospital.appointment") or "New"
        recs = super().create(vals_list)
        recs._assign_queue_number()
        return recs

    def unlink(self):
        privileged = self.env.user.has_group(
            "smart_hospital_appointment.group_hospital_admin"
        ) or self.env.user.has_group("smart_hospital_appointment.group_hospital_receptionist")
        if not privileged:
            bad = self.filtered(lambda r: r.state not in ("draft", "confirmed"))
            if bad:
                raise UserError(_("You can only delete appointments that are still in draft or confirmed."))
        return super().unlink()

    def write(self, vals):
        if "patient_id" in vals and vals.get("state") != "draft":
            blocked = self.filtered(lambda r: r.state in ("completed", "released", "cancelled"))
            if blocked:
                raise ValidationError(_("The patient cannot be changed when the appointment is completed, released, or cancelled."))
        if "medicine_line_ids" in vals:
            if any(r.state == "released" for r in self):
                raise ValidationError(_("Prescribed medicines cannot be changed after the patient is released."))
            not_done = self.filtered(lambda r: r.state != "completed")
            if not_done and vals.get("state") != "completed":
                raise ValidationError(_("Prescribed medicines can only be edited after the appointment is completed."))
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
            if rec.state in ("cancelled", "released"):
                continue
            overlap_domain = [
                ("id", "!=", rec.id),
                ("doctor_id", "=", rec.doctor_id.id),
                ("appointment_datetime", "=", rec.appointment_datetime),
                ("state", "not in", ("cancelled", "released")),
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
            if (
                not rec.appointment_datetime
                or rec.state
                in ("in_progress", "completed", "released", "cancelled")
            ):
                rec.estimated_wait_minutes = 0
                continue
            day_start, day_end = rec._appointment_day_bounds()
            queue_domain = [
                ("doctor_id", "=", rec.doctor_id.id),
                ("branch_id", "=", rec.branch_id.id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "in", ("draft", "confirmed", "in_progress", "completed")),
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

    @api.depends("appointment_datetime", "estimated_wait_minutes", "state")
    def _compute_expected_turn_datetime(self):
        for rec in self:
            if (
                not rec.appointment_datetime
                or rec.state in ("released", "cancelled", "in_progress", "completed")
            ):
                rec.expected_turn_datetime = False
                continue
            base = fields.Datetime.to_datetime(rec.appointment_datetime)
            rec.expected_turn_datetime = base + timedelta(minutes=rec.estimated_wait_minutes or 0)

    def _appointment_day_bounds(self):
        self.ensure_one()
        dt = fields.Datetime.to_datetime(self.appointment_datetime)
        day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start, day_start + timedelta(days=1)

    def _get_average_consultation_minutes(self):
        self.ensure_one()
        done = self.search(
            [
                ("doctor_id", "=", self.doctor_id.id),
                ("state", "in", ("completed", "released")),
                ("completion_minutes", ">", 0),
            ],
            limit=50,
            order="id desc",
        )
        if not done:
            return 30
        return max(5, sum(done.mapped("completion_minutes")) / len(done))

    def _assign_queue_number(self):
        keys = set()
        for appt in self:
            if not appt.appointment_datetime or not appt.doctor_id or not appt.branch_id:
                continue
            day_start, day_end = appt._appointment_day_bounds()
            keys.add((appt.doctor_id.id, appt.branch_id.id, day_start, day_end))
        for doctor_id, branch_id, day_start, day_end in keys:
            active_domain = [
                ("doctor_id", "=", doctor_id),
                ("branch_id", "=", branch_id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "in", ("draft", "confirmed", "in_progress", "completed")),
            ]
            daily = self.search(active_domain, order="is_high_priority desc, appointment_datetime asc, id asc")
            for idx, appt in enumerate(daily, start=1):
                appt.write({"queue_number": idx})
            clear_domain = [
                ("doctor_id", "=", doctor_id),
                ("branch_id", "=", branch_id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "in", ("released", "cancelled")),
                ("queue_number", "!=", 0),
            ]
            to_clear = self.search(clear_domain)
            if to_clear:
                to_clear.write({"queue_number": 0})

    def _same_day_active_queue_appointments(self):
        self.ensure_one()
        day_start, day_end = self._appointment_day_bounds()
        return self.search(
            [
                ("doctor_id", "=", self.doctor_id.id),
                ("branch_id", "=", self.branch_id.id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "in", ("draft", "confirmed", "in_progress", "completed")),
            ],
            order="is_high_priority desc, appointment_datetime asc, id asc",
        )

    def _ensure_can_start_consultation(self):
        self.ensure_one()
        day_start, day_end = self._appointment_day_bounds()
        other_ip = self.search(
            [
                ("id", "!=", self.id),
                ("doctor_id", "=", self.doctor_id.id),
                ("branch_id", "=", self.branch_id.id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "=", "in_progress"),
            ],
            limit=1,
        )
        if other_ip:
            raise UserError(_("Another patient is already in consultation with this doctor today."))
        ordered = self._same_day_active_queue_appointments()
        if self not in ordered:
            return
        idx = ordered.ids.index(self.id)
        blocking_states = ("confirmed", "in_progress", "completed")
        for ahead in ordered[:idx]:
            if ahead.state in blocking_states:
                raise UserError(
                    _(
                        "You must release earlier patients (or wait until their visit is finished) "
                        "before starting the next consultation. Blocking appointment: %s"
                    )
                    % ahead.display_name
                )

    def action_confirm(self):
        can_schedule_activity = self.env.user.has_group("base.group_user")
        for rec in self:
            if rec.doctor_id.is_unavailable:
                rec.action_suggest_reschedule()
                raise UserError(_("Doctor is marked unavailable. A next available slot was suggested."))
            rec.state = "confirmed"
            if can_schedule_activity:
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Upcoming Appointment"),
                    note=_("Appointment %s is confirmed for %s.")
                    % (rec.name, fields.Datetime.to_string(rec.appointment_datetime)),
                    user_id=rec.doctor_id.user_id.id or self.env.user.id,
                )
        self._assign_queue_number()

    def action_in_progress(self):
        for rec in self:
            rec._ensure_can_start_consultation()
        self.write({"state": "in_progress"})
        self._assign_queue_number()

    def action_complete(self):
        for rec in self:
            rec.state = "completed"
            if not rec.completion_minutes:
                rec.completion_minutes = rec.duration_minutes
        self._assign_queue_number()

    def action_release(self):
        for rec in self:
            if rec.state != "completed":
                raise UserError(_("Only a completed appointment can be marked as released."))
        self.write({"state": "released"})
        self._assign_queue_number()

    def action_print_medicine_prescription(self):
        invalid = self.filtered(lambda a: a.state not in ("completed", "released"))
        if invalid:
            raise UserError(_("You can only print the medicine report for completed or released appointments."))
        return self.env.ref(
            "smart_hospital_appointment.action_report_hospital_medicine_prescription"
        ).report_action(self)

    def action_cancel(self):
        self.write({"state": "cancelled"})
        self._assign_queue_number()

    def action_set_to_draft(self):
        invalid = self.filtered(lambda r: r.state != "cancelled")
        if invalid:
            raise UserError(_("Only cancelled appointments can be set back to draft."))
        self.write({"state": "draft"})
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
                            ("state", "not in", ("cancelled", "released")),
                        ]
                    )
                    if not clash:
                        return fields.Datetime.to_string(check)
                    check += timedelta(minutes=slot.slot_minutes)
            current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return False

    def _get_slot_grace_minutes(self):
        """Grace after scheduled slot start (from doctor availability slot length, e.g. 10 or 15 min)."""
        self.ensure_one()
        if not self.appointment_datetime or not self.doctor_id:
            return 15
        appt_dt = fields.Datetime.context_timestamp(self, self.appointment_datetime)
        weekday = str(appt_dt.weekday())
        slots = self.doctor_id.availability_ids.filtered(
            lambda s: s.branch_id == self.branch_id and s.day_of_week == weekday
        )
        if not slots:
            return 15
        return max(5, max(slots.mapped("slot_minutes")))

    def _is_late_for_slot(self):
        self.ensure_one()
        if self.state != "confirmed" or not self.appointment_datetime:
            return False
        grace = self._get_slot_grace_minutes()
        slot_start = fields.Datetime.to_datetime(self.appointment_datetime)
        deadline = slot_start + timedelta(minutes=grace)
        return fields.Datetime.now() > deadline

    def _late_swap_with_next_if_needed(self):
        """If this confirmed patient is past slot grace, swap appointment time with the next confirmed in queue."""
        self.ensure_one()
        if not self._is_late_for_slot():
            return False
        day_start, day_end = self._appointment_day_bounds()
        waiting = self.search(
            [
                ("doctor_id", "=", self.doctor_id.id),
                ("branch_id", "=", self.branch_id.id),
                ("appointment_datetime", ">=", day_start),
                ("appointment_datetime", "<", day_end),
                ("state", "=", "confirmed"),
            ],
            order="queue_number asc, id asc",
        )
        ids_list = waiting.ids
        if self.id not in ids_list:
            return False
        idx = ids_list.index(self.id)
        if idx >= len(ids_list) - 1:
            return False
        next_appt = waiting[idx + 1]
        dt_self = self.appointment_datetime
        dt_next = next_appt.appointment_datetime
        self.write({"appointment_datetime": dt_next})
        next_appt.write({"appointment_datetime": dt_self})
        (self | next_appt)._assign_queue_number()
        return True

    @api.model
    def cron_late_queue_swap(self):
        """Background job: swap late confirmed patients with the next slot (same doctor/branch/day)."""
        swapped = True
        rounds = 0
        while swapped and rounds < 30:
            swapped = False
            rounds += 1
            for appt in self.search([("state", "=", "confirmed")], order="id"):
                if appt._late_swap_with_next_if_needed():
                    swapped = True

    @api.model
    def cron_resequence_queue(self):
        appointments = self.search(
            [("state", "in", ("draft", "confirmed", "in_progress", "completed"))],
            order="doctor_id, branch_id, appointment_datetime asc",
        )
        appointments._assign_queue_number()
