# -*- coding: utf-8 -*-

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

    def _portal_parse_datetime(self, value=None, date_value=None, time_value=None):
        if date_value or time_value:
            if not date_value or not time_value:
                raise UserError(_("Please set a date and time for the appointment."))
            value = f"{date_value} {time_value}"
        if not value:
            raise UserError(_("Please set a date and time for the appointment."))
        norm = value.replace("T", " ")
        if len(norm) == 16:
            norm += ":00"
        naive_local = datetime.strptime(norm, "%Y-%m-%d %H:%M:%S")
        tz = pytz.timezone(request.env.user.tz or "UTC")
        localized = tz.localize(naive_local)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

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

    def _get_doctor_start_time(self, doctor, branch, date_value=None):
        if not doctor or not branch:
            return ""
        slots = request.env["hospital.doctor.availability"].sudo().search(
            [
                ("doctor_id", "=", doctor.id),
                ("branch_id", "=", branch.id),
            ],
            order="day_of_week, start_time",
        )
        if not slots:
            return ""
        if date_value:
            try:
                day = str(datetime.strptime(date_value, "%Y-%m-%d").weekday())
                slots = slots.filtered(lambda slot: slot.day_of_week == day)
            except ValueError:
                pass
        if not slots:
            return ""
        return self._float_hours_to_time_str(slots[0].start_time)

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
        start_time = self._get_doctor_start_time(doctor, branch, appointment_date_input)
        if start_time and (not appointment or post.get("doctor_id") or post.get("appointment_date")):
            appointment_time_input = start_time
        return {
            "appointment": appointment,
            "appointment_date_input": appointment_date_input,
            "appointment_time_input": appointment_time_input,
            "portal_partner": partner,
            "doctors": doctors,
            "branches": branches,
            "specializations": specializations,
            "error": {},
            "post": post,
            "selected_doctor_id": selected_doctor_id,
            "selected_branch_id": selected_branch_id,
            "selected_specialization_id": selected_specialization_id,
            "page_name": page_name,
            "form_action": form_action,
            "default_url": default_url,
        }

    def _submit_appointment_form(self, partner, post, appointment=None):
        doctor = request.env["hospital.doctor"].sudo().browse(int(post.get("doctor_id") or 0))
        branch = request.env["hospital.branch"].sudo().browse(int(post.get("branch_id") or 0))
        if not doctor.exists() or not branch.exists():
            raise UserError(_("Please select a valid doctor and branch."))
        if branch not in doctor.branch_ids:
            raise UserError(_("This doctor does not work at the selected branch."))
        appt_dt = self._portal_parse_datetime(
            date_value=post.get("appointment_date"),
            time_value=post.get("appointment_time"),
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
    def portal_my_hospital(self, page=1, filterby="all", **kw):
        values = self._prepare_hospital_portal_layout()
        partner = values["portal_partner"]
        Appointment = request.env["hospital.appointment"]
        domain = [("patient_id", "=", partner.id)]
        filters = {
            "all": [],
            "upcoming": [("state", "=", "confirmed")],
            "pending": [("state", "=", "draft")],
            "completed": [("state", "in", ("completed", "released"))],
            "cancelled": [("state", "=", "cancelled")],
        }
        if filterby not in filters:
            filterby = "all"
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
                "pending_count": Appointment.search_count(
                    domain + [("state", "=", "draft")]
                ),
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
                return request.redirect(f"/my/hospital/appointment/{appt.id}")
            except (UserError, ValidationError, AccessError, ValueError) as e:
                values["error"] = {"message": str(e)}
                values.update(
                    self._prepare_appointment_form_values(
                        post=post,
                        page_name="hospital_new",
                        form_action="/my/hospital/appointment/new",
                    )
                )
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
        values["appointment"] = appt
        values["default_url"] = "/my/hospital"
        return request.render("smart_hospital_appointment.portal_hospital_appointment_detail", values)

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
        if appt.state not in ("draft", "confirmed"):
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
                values["error"] = {"message": str(e)}
                values.update(
                    self._prepare_appointment_form_values(
                        appointment=appt,
                        post=post,
                        page_name="hospital_edit",
                        form_action=f"/my/hospital/appointment/{appointment_id}/edit",
                    )
                )
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
            if appt.state in ("draft", "confirmed", "in_progress"):
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
