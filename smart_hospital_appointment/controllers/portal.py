# -*- coding: utf-8 -*-

import json
from datetime import datetime

import pytz

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

try:
    from odoo.addons.appointment.controllers.portal import AppointmentPortal
except Exception:  # appointment module may be unavailable
    AppointmentPortal = None


class HospitalBookingMixin:
    def _get_portal_partner(self):
        return request.env.user.partner_id

    def _portal_parse_datetime(
        self, value=None, date_value=None, time_value=None, allow_past_time_today=False
    ):
        """Parse the local date/time entered on the portal and return it as naive UTC.

        allow_past_time_today: accept a time earlier than now when the date is today, for
        queue bookings stamped with the doctor's shift start while the shift is still running.
        """
        if date_value or time_value:
            if not date_value or not time_value:
                raise UserError(_("Please set a date and time for the appointment."))
            value = f"{date_value} {time_value}"
        if not value:
            raise UserError(_("Please set a date and time for the appointment."))
        norm = value.replace("T", " ")
        if len(norm) == 16:
            norm += ":00"
        try:
            naive_local = datetime.strptime(norm, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise UserError(_("The appointment date or time is not valid. Please pick it again."))
        tz = pytz.timezone(request.env.user.tz or "UTC")
        localized = tz.localize(naive_local)
        now_local = datetime.now(tz)
        if localized.date() < now_local.date():
            raise UserError(
                _("You cannot book an appointment on a past date (%s). Please choose today or a future date.")
                % localized.strftime("%d %b %Y")
            )
        if localized < now_local and not (
            allow_past_time_today and localized.date() == now_local.date()
        ):
            raise UserError(
                _("The selected time (%s) has already passed. Please choose a later time or another date.")
                % localized.strftime("%d %b %Y %H:%M")
            )
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _get_doctor_day_slots(self, doctor, branch, date_value):
        """Availability slots of the doctor at the branch on the weekday of date_value."""
        if not doctor or not branch or not date_value:
            return request.env["hospital.doctor.availability"]
        try:
            day = str(datetime.strptime(date_value, "%Y-%m-%d").weekday())
        except ValueError:
            return request.env["hospital.doctor.availability"]
        return request.env["hospital.doctor.availability"].sudo().search(
            [
                ("doctor_id", "=", doctor.id),
                ("branch_id", "=", branch.id),
                ("day_of_week", "=", day),
            ],
            order="start_time",
        )

    _WEEKDAY_LABELS = {
        "0": "Monday",
        "1": "Tuesday",
        "2": "Wednesday",
        "3": "Thursday",
        "4": "Friday",
        "5": "Saturday",
        "6": "Sunday",
    }

    def _float_hours_to_time_str(self, value):
        if value is False or value is None:
            return ""
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes >= 60:
            hours += 1
            minutes = 0
        hours %= 24
        return f"{hours:02d}:{minutes:02d}"

    def _format_float_time_ampm(self, value):
        time_str = self._float_hours_to_time_str(value)
        if not time_str:
            return ""
        hours, minutes = map(int, time_str.split(":"))
        period = "AM" if hours < 12 else "PM"
        hours12 = hours % 12 or 12
        return f"{hours12:02d}:{minutes:02d} {period}"

    def _get_doctor_branch_slots(self, doctor, branch):
        if not doctor or not branch:
            return request.env["hospital.doctor.availability"]
        return request.env["hospital.doctor.availability"].sudo().search(
            [
                ("doctor_id", "=", doctor.id),
                ("branch_id", "=", branch.id),
            ],
            order="day_of_week, start_time",
        )

    def _get_doctor_available_weekdays(self, doctor, branch):
        """Weekday numbers (0=Mon … 6=Sun) the doctor works at the branch."""
        slots = self._get_doctor_branch_slots(doctor, branch)
        return sorted({int(day) for day in slots.mapped("day_of_week")}, key=int)

    def _get_doctor_available_weekday_labels(self, doctor, branch):
        return [
            self._WEEKDAY_LABELS[str(day)]
            for day in self._get_doctor_available_weekdays(doctor, branch)
        ]

    def _get_doctor_day_time_display(self, doctor, branch, date_value):
        """Human-readable start–end windows for the doctor on that date."""
        slots = self._get_doctor_day_slots(doctor, branch, date_value)
        if not slots:
            return ""
        return ", ".join(
            f"{self._format_float_time_ampm(slot.start_time)} – {self._format_float_time_ampm(slot.end_time)}"
            for slot in slots
        )

    def _get_doctor_start_time(self, doctor, branch, date_value=None):
        if not doctor or not branch:
            return ""
        if date_value:
            slots = self._get_doctor_day_slots(doctor, branch, date_value)
        else:
            slots = self._get_doctor_branch_slots(doctor, branch)
        if not slots:
            return ""
        return self._float_hours_to_time_str(slots[0].start_time)

    def _is_available_booking_date(self, doctor, branch, date_value):
        if not date_value or not doctor or not branch:
            return False
        try:
            day = datetime.strptime(date_value, "%Y-%m-%d").weekday()
        except ValueError:
            return False
        return day in self._get_doctor_available_weekdays(doctor, branch)

    def _get_booking_branches(self):
        return request.env["hospital.branch"].sudo().search([("active", "=", True)], order="name")

    def _get_booking_doctors(self, branch=None, specialization=None):
        domain = [("active", "=", True), ("is_unavailable", "=", False)]
        if branch:
            domain.append(("branch_ids", "in", [branch.id]))
        if specialization:
            domain.append(("specialization", "=", specialization.id))
        return request.env["hospital.doctor"].sudo().search(domain, order="name")

    def _get_booking_specializations(self, branch=None):
        return self._get_booking_doctors(branch=branch).mapped("specialization").sorted("name")

    def _resolve_booking_selection(self, post, appointment=None):
        branch_id = int(post.get("branch_id") or 0)
        specialization_id = int(post.get("specialization_id") or 0)
        doctor_id = int(post.get("doctor_id") or 0)
        if appointment:
            branch_id = branch_id or appointment.branch_id.id
            doctor_id = doctor_id or appointment.doctor_id.id
            specialization_id = specialization_id or appointment.doctor_id.specialization.id
        elif doctor_id:
            doctor = request.env["hospital.doctor"].sudo().browse(doctor_id)
            if doctor.exists():
                specialization_id = specialization_id or doctor.specialization.id
                if not branch_id and doctor.branch_ids:
                    branch_id = doctor.branch_ids[0].id
        return branch_id, specialization_id, doctor_id

    def _prepare_appointment_form_values(
        self,
        *,
        appointment=None,
        post=None,
        page_name="hospital_new",
        form_action=None,
        default_url="/my/hospital",
    ):
        post = post or {}
        partner = self._get_portal_partner()
        branches = self._get_booking_branches()
        selected_branch_id, selected_specialization_id, selected_doctor_id = self._resolve_booking_selection(
            post, appointment=appointment
        )
        branch = branches.filtered(lambda b: b.id == selected_branch_id)[:1]
        specializations = (
            self._get_booking_specializations(branch=branch)
            if branch
            else request.env["hospital.specialization"]
        )
        if selected_specialization_id and selected_specialization_id not in specializations.ids:
            selected_specialization_id = 0
        specialization = specializations.filtered(lambda s: s.id == selected_specialization_id)[:1]
        doctors = (
            self._get_booking_doctors(branch=branch, specialization=specialization)
            if branch and specialization
            else request.env["hospital.doctor"]
        )
        if selected_doctor_id and selected_doctor_id not in doctors.ids:
            selected_doctor_id = 0
        doctor = doctors.filtered(lambda rec: rec.id == selected_doctor_id)[:1]
        appointment_date_input = post.get("appointment_date") or ""
        appointment_time_input = post.get("appointment_time") or ""
        if appointment and not appointment_date_input:
            ctx_dt = fields.Datetime.context_timestamp(appointment, appointment.appointment_datetime)
            appointment_date_input = ctx_dt.strftime("%Y-%m-%d")
            appointment_time_input = appointment_time_input or ctx_dt.strftime("%H:%M")
        available_weekdays = self._get_doctor_available_weekdays(doctor, branch)
        if appointment_date_input and doctor and branch and not self._is_available_booking_date(
            doctor, branch, appointment_date_input
        ):
            # Clear a date that falls on a day the doctor does not work.
            appointment_date_input = ""
            appointment_time_input = ""
        start_time = self._get_doctor_start_time(doctor, branch, appointment_date_input)
        if start_time and (not appointment or post.get("doctor_id") or post.get("appointment_date")):
            appointment_time_input = start_time
        appointment_time_display = self._get_doctor_day_time_display(
            doctor, branch, appointment_date_input
        )
        return {
            "appointment": appointment,
            "appointment_date_input": appointment_date_input,
            "appointment_time_input": appointment_time_input,
            "appointment_time_display": appointment_time_display,
            "available_weekdays": available_weekdays,
            "available_weekdays_json": json.dumps(available_weekdays),
            "available_weekday_labels": self._get_doctor_available_weekday_labels(doctor, branch),
            "portal_partner": partner,
            "doctors": doctors,
            "branches": branches,
            "specializations": specializations,
            "error": {},
            "min_booking_date": datetime.now(pytz.timezone(request.env.user.tz or "UTC")).strftime("%Y-%m-%d"),
            "post": post,
            "selected_doctor_id": selected_doctor_id,
            "selected_branch_id": selected_branch_id,
            "selected_specialization_id": selected_specialization_id,
            "page_name": page_name,
            "form_action": form_action,
            "default_url": default_url,
        }

    def _get_post_booking_url(self, appointment):
        if appointment._has_to_be_paid():
            return f"/my/hospital/appointment/{appointment.id}/pay"
        return f"/my/hospital/appointment/{appointment.id}"

    def _submit_appointment_form(self, partner, post, appointment=None):
        doctor = request.env["hospital.doctor"].sudo().browse(int(post.get("doctor_id") or 0))
        branch = request.env["hospital.branch"].sudo().browse(int(post.get("branch_id") or 0))
        if not doctor.exists() or not branch.exists():
            raise UserError(_("Please select a valid doctor and branch."))
        if branch not in doctor.branch_ids:
            raise UserError(_("This doctor does not work at the selected branch."))
        if not doctor.active or doctor.is_unavailable:
            raise UserError(_("Dr. %s is not available for booking right now. Please choose another doctor.") % doctor.name)
        date_value = post.get("appointment_date")
        if not date_value:
            raise UserError(_("Please choose a date for the appointment."))
        slots = self._get_doctor_day_slots(doctor, branch, date_value)
        if not slots:
            raise UserError(
                _("Dr. %(doctor)s has no schedule at %(branch)s on the selected day. Please choose another date.",
                  doctor=doctor.name, branch=branch.name)
            )
        now_local = datetime.now(pytz.timezone(request.env.user.tz or "UTC"))
        if date_value == now_local.strftime("%Y-%m-%d"):
            now_float = now_local.hour + now_local.minute / 60.0
            slots = slots.filtered(lambda slot: slot.end_time > now_float)
            if not slots:
                raise UserError(
                    _("Dr. %(doctor)s's schedule at %(branch)s has already ended for today. Please choose another date.",
                      doctor=doctor.name, branch=branch.name)
                )
        start_time = self._float_hours_to_time_str(slots[0].start_time)
        appt_dt = self._portal_parse_datetime(
            date_value=date_value, time_value=start_time, allow_past_time_today=True
        )
        vals = {
            "patient_id": partner.id,
            "doctor_id": doctor.id,
            "branch_id": branch.id,
            "appointment_datetime": fields.Datetime.to_string(appt_dt),
            "notes": post.get("notes") or False,
        }
        with request.env.cr.savepoint():
            if appointment:
                appointment.write(vals)
                return appointment
            appt = request.env["hospital.appointment"].sudo().create(vals)
            appt.action_confirm()
            return appt


class HospitalPortal(HospitalBookingMixin, CustomerPortal):
    _items_per_page = 20

    def _prepare_hospital_portal_layout(self, page_name="hospital"):
        values = self._prepare_portal_layout_values()
        partner = self._get_portal_partner()
        values.update(
            {
                "page_name": page_name,
                "portal_partner": partner,
            }
        )
        return values

    @http.route(["/my/hospital", "/my/hospital/page/<int:page>"], type="http", auth="user", website=True)
    def portal_my_hospital(self, page=1, filterby="upcoming", **kw):
        values = self._prepare_hospital_portal_layout()
        partner = values["portal_partner"]
        Appointment = request.env["hospital.appointment"]
        domain = [("patient_id", "=", partner.id)]
        filters = {
            "all": [],
            "upcoming": [("state", "=", "confirmed")],
            "completed": [("state", "in", ("completed", "released"))],
            "cancelled": [("state", "=", "cancelled")],
        }
        if filterby not in filters:
            filterby = "upcoming"
        list_domain = domain + filters[filterby]
        total = Appointment.search_count(domain)
        filtered_total = Appointment.search_count(list_domain)
        pager = portal_pager(
            url="/my/hospital",
            url_args={"filterby": filterby},
            total=filtered_total,
            page=page,
            step=self._items_per_page,
        )
        appointments = Appointment.search(
            list_domain,
            order="appointment_datetime desc",
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        values.update(
            {
                "appointments": appointments,
                "pager": pager,
                "default_url": "/my/hospital",
                "filterby": filterby,
                "appointment_count": total,
                "upcoming_count": Appointment.search_count(
                    domain + [("state", "=", "confirmed")]
                ),
                "completed_count": Appointment.search_count(
                    domain + [("state", "in", ("completed", "released"))]
                ),
                "cancelled_count": Appointment.search_count(
                    domain + [("state", "=", "cancelled")]
                ),
            }
        )
        return request.render("smart_hospital_appointment.portal_my_hospital", values)

    @http.route(
        ["/my/hospital/appointment/new"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_hospital_appointment_new(self, **post):
        values = self._prepare_hospital_portal_layout(page_name="hospital_new")
        form_values = self._prepare_appointment_form_values(
            post=post,
            page_name="hospital_new",
            form_action="/my/hospital/appointment/new",
        )
        values.update(form_values)
        if request.httprequest.method == "POST" and post:
            try:
                appt = self._submit_appointment_form(values["portal_partner"], post)
                return request.redirect(self._get_post_booking_url(appt))
            except (UserError, ValidationError, AccessError, ValueError) as e:
                values.update(
                    self._prepare_appointment_form_values(
                        post=post,
                        page_name="hospital_new",
                        form_action="/my/hospital/appointment/new",
                    )
                )
                values["error"] = {"message": str(e)}
        return request.render("smart_hospital_appointment.portal_hospital_appointment_form", values)

    def _get_portal_appointment(self, appointment_id):
        appt = request.env["hospital.appointment"].browse(appointment_id)
        if not appt.exists() or appt.patient_id != request.env.user.partner_id:
            raise AccessError(_("You cannot access this appointment."))
        return appt

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_hospital_appointment_detail(self, appointment_id, **kw):
        values = self._prepare_hospital_portal_layout(page_name="hospital_detail")
        try:
            appt = self._get_portal_appointment(appointment_id)
        except AccessError:
            return request.redirect("/my/hospital")
        date_value = fields.Datetime.context_timestamp(appt, appt.appointment_datetime).strftime("%Y-%m-%d")
        values["appointment"] = appt
        values["doctor_hours_display"] = self._get_doctor_day_time_display(
            appt.doctor_id, appt.branch_id, date_value
        )
        values["default_url"] = "/my/hospital"
        return request.render("smart_hospital_appointment.portal_hospital_appointment_detail", values)

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/live"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_hospital_appointment_live(self, appointment_id, **kw):
        values = self._prepare_hospital_portal_layout(page_name="hospital_live")
        try:
            appt = self._get_portal_appointment(appointment_id)
        except AccessError:
            return request.redirect("/my/hospital")
        values.update(
            {
                "appointment": appt,
                "default_url": "/my/hospital",
                "live_data_url": f"/my/hospital/appointment/{appointment_id}/live/data",
            }
        )
        return request.render("smart_hospital_appointment.portal_hospital_appointment_live", values)

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/live/data"],
        type="http",
        auth="user",
        methods=["GET"],
    )
    def portal_hospital_appointment_live_data(self, appointment_id, **kw):
        try:
            appt = self._get_portal_appointment(appointment_id)
        except AccessError:
            return request.make_json_response({"error": "not_found"}, status=404)
        return request.make_json_response(appt._get_live_queue_data())

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/edit"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def portal_hospital_appointment_edit(self, appointment_id, **post):
        values = self._prepare_hospital_portal_layout(page_name="hospital_edit")
        try:
            appt = self._get_portal_appointment(appointment_id)
        except AccessError:
            return request.redirect("/my/hospital")
        if appt.state not in ("draft", "confirmed") or appt._is_payment_locked():
            return request.redirect(f"/my/hospital/appointment/{appointment_id}")
        form_values = self._prepare_appointment_form_values(
            appointment=appt,
            post=post,
            page_name="hospital_edit",
            form_action=f"/my/hospital/appointment/{appointment_id}/edit",
        )
        values.update(form_values)
        if request.httprequest.method == "POST" and post:
            try:
                self._submit_appointment_form(values["portal_partner"], post, appointment=appt)
                return request.redirect(f"/my/hospital/appointment/{appointment_id}")
            except (UserError, ValidationError, AccessError, ValueError) as e:
                values.update(
                    self._prepare_appointment_form_values(
                        appointment=appt,
                        post=post,
                        page_name="hospital_edit",
                        form_action=f"/my/hospital/appointment/{appointment_id}/edit",
                    )
                )
                values["error"] = {"message": str(e)}
                values["appointment_date_input"] = post.get("appointment_date") or values[
                    "appointment_date_input"
                ]
                values["appointment_time_input"] = post.get("appointment_time") or values[
                    "appointment_time_input"
                ]
        return request.render("smart_hospital_appointment.portal_hospital_appointment_form", values)

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/confirm"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_hospital_appointment_confirm(self, appointment_id, **post):
        try:
            appt = self._get_portal_appointment(appointment_id)
            if appt.state == "draft":
                appt.action_confirm()
        except (AccessError, UserError):
            pass
        return request.redirect(f"/my/hospital/appointment/{appointment_id}")

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/medicine-report"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_hospital_appointment_medicine_report(self, appointment_id, **kw):
        try:
            appt = self._get_portal_appointment(appointment_id)
        except AccessError:
            return request.redirect("/my/hospital")
        if appt.state not in ("completed", "released"):
            return request.redirect(f"/my/hospital/appointment/{appointment_id}")
        return self._show_report(
            model=appt,
            report_type="pdf",
            report_ref="smart_hospital_appointment.action_report_hospital_medicine_prescription",
            download=True,
        )

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/cancel"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def portal_hospital_appointment_cancel(self, appointment_id, **post):
        try:
            appt = self._get_portal_appointment(appointment_id)
            if appt.state in ("draft", "confirmed", "in_progress") and not appt._is_payment_locked():
                appt.action_cancel()
        except (AccessError, UserError):
            pass
        return request.redirect(f"/my/hospital/appointment/{appointment_id}")


if AppointmentPortal:
    class HospitalPortalAppointmentOverride(AppointmentPortal):
        @http.route(
            ["/my/appointments", "/my/appointments/page/<int:page>"],
            type="http",
            auth="user",
            website=True,
        )
        def portal_my_appointments(self, page=1, **kwargs):
            return request.redirect(f"/my/hospital/page/{page}" if page and page > 1 else "/my/hospital")
