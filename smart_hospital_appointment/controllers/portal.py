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

    def _portal_parse_datetime(self, value):
        if not value:
            raise UserError(_("Please set a date and time for the appointment."))
        norm = value.replace("T", " ")
        if len(norm) == 16:
            norm += ":00"
        naive_local = datetime.strptime(norm, "%Y-%m-%d %H:%M:%S")
        tz = pytz.timezone(request.env.user.tz or "UTC")
        localized = tz.localize(naive_local)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _get_booking_doctors(self):
        return request.env["hospital.doctor"].search(
            [("active", "=", True), ("is_unavailable", "=", False)],
            order="name",
        )

    def _get_booking_branches(self, doctor=None):
        branches = request.env["hospital.branch"].search([("active", "=", True)], order="name")
        if doctor:
            branches = branches.filtered(lambda branch: branch in doctor.branch_ids)
        return branches

    def _resolve_booking_selection(self, post, doctors, branches, appointment=None):
        doctor_id = int(post.get("doctor_id") or 0)
        branch_id = int(post.get("branch_id") or 0)
        if appointment:
            doctor_id = doctor_id or appointment.doctor_id.id
            branch_id = branch_id or appointment.branch_id.id
        if not doctor_id and doctors:
            doctor_id = doctors[0].id
        if not branch_id and branches:
            branch_id = branches[0].id
        return doctor_id, branch_id

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
        doctors = self._get_booking_doctors()
        selected_doctor_id, selected_branch_id = self._resolve_booking_selection(
            post, doctors, request.env["hospital.branch"], appointment=appointment
        )
        doctor = doctors.filtered(lambda d: d.id == selected_doctor_id)[:1]
        branches = self._get_booking_branches(doctor)
        if selected_branch_id and selected_branch_id not in branches.ids:
            selected_branch_id = branches[:1].id if branches else 0
        appointment_datetime_input = ""
        if appointment:
            ctx_dt = fields.Datetime.context_timestamp(appointment, appointment.appointment_datetime)
            appointment_datetime_input = ctx_dt.strftime("%Y-%m-%dT%H:%M")
        return {
            "appointment": appointment,
            "appointment_datetime_input": appointment_datetime_input,
            "portal_partner": partner,
            "doctors": doctors,
            "branches": branches,
            "error": {},
            "post": post,
            "selected_doctor_id": selected_doctor_id,
            "selected_branch_id": selected_branch_id,
            "page_name": page_name,
            "form_action": form_action,
            "default_url": default_url,
        }

    def _submit_appointment_form(self, partner, post, appointment=None):
        doctor = request.env["hospital.doctor"].browse(int(post.get("doctor_id", 0)))
        branch = request.env["hospital.branch"].browse(int(post.get("branch_id", 0)))
        if not doctor.exists() or not branch.exists():
            raise UserError(_("Please select a valid doctor and branch."))
        if branch not in doctor.branch_ids:
            raise UserError(_("This doctor does not work at the selected branch."))
        appt_dt = self._portal_parse_datetime(post.get("appointment_datetime"))
        vals = {
            "patient_id": partner.id,
            "doctor_id": doctor.id,
            "branch_id": branch.id,
            "appointment_datetime": fields.Datetime.to_string(appt_dt),
            "duration_minutes": int(post.get("duration_minutes") or 30),
            "notes": post.get("notes") or False,
        }
        with request.env.cr.savepoint():
            if appointment:
                appointment.write(vals)
                return appointment
            appt = request.env["hospital.appointment"].create(vals)
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
    def portal_my_hospital(self, page=1, **kw):
        values = self._prepare_hospital_portal_layout()
        partner = values["portal_partner"]
        Appointment = request.env["hospital.appointment"]
        domain = [("patient_id", "=", partner.id)]
        total = Appointment.search_count(domain)
        pager = portal_pager(
            url="/my/hospital",
            total=total,
            page=page,
            step=self._items_per_page,
        )
        appointments = Appointment.search(
            domain,
            order="appointment_datetime desc",
            limit=self._items_per_page,
            offset=pager["offset"],
        )
        values.update(
            {
                "appointments": appointments,
                "pager": pager,
                "default_url": "/my/hospital",
                "appointment_count": total,
                "upcoming_count": Appointment.search_count(
                    domain + [("state", "in", ("draft", "confirmed", "in_progress"))]
                ),
                "completed_count": Appointment.search_count(
                    domain + [("state", "in", ("completed", "released"))]
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
                values["appointment_datetime_input"] = post.get("appointment_datetime") or values[
                    "appointment_datetime_input"
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
