# -*- coding: utf-8 -*-

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .portal import HospitalBookingMixin

try:
    from odoo.addons.auth_signup.models.res_users import SignupError
except ImportError:
    SignupError = UserError

try:
    from odoo.addons.website.controllers.main import Website
except ImportError:
    Website = None


class HospitalWebsite(HospitalBookingMixin, http.Controller):
    @http.route(["/doctors"], type="http", auth="public", website=True, sitemap=True)
    def doctors_list(self, **kw):
        doctors = request.env["hospital.doctor"].sudo().search(
            [("active", "=", True), ("is_unavailable", "=", False)],
            order="name",
        )
        return request.render(
            "smart_hospital_appointment.website_doctors_list",
            {
                "doctors": doctors,
                "doctor_count": len(doctors),
                "branch_count": len(doctors.mapped("branch_ids")),
            },
        )

    @http.route(
        ["/appointment/book", "/appointments/book"],
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        sitemap=True,
    )
    def website_appointment_book(self, **post):
        values = self._prepare_appointment_form_values(
            post=post,
            page_name="website_book",
            form_action="/appointment/book",
        )
        if request.httprequest.method == "POST" and post:
            try:
                appt = self._submit_appointment_form(values["portal_partner"], post)
                return request.redirect(f"/my/hospital/appointment/{appt.id}")
            except (UserError, ValidationError, AccessError, ValueError) as e:
                values["error"] = {"message": str(e)}
                values.update(
                    self._prepare_appointment_form_values(
                        post=post,
                        page_name="website_book",
                        form_action="/appointment/book",
                    )
                )
        return request.render("smart_hospital_appointment.website_appointment_book", values)

    @http.route(
        ["/appointment/register", "/appointments/register"],
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
        sitemap=True,
    )
    def website_patient_register(self, **post):
        if request.env.user.has_group("base.group_portal") or request.env.user.has_group("base.group_user"):
            if not request.env.user._is_public():
                return request.redirect("/appointment/book")

        branches = request.env["hospital.branch"].sudo().search([("active", "=", True)], order="name")
        values = {
            "branches": branches,
            "post": post,
            "error": False,
        }
        if request.httprequest.method == "POST" and post:
            try:
                user, _patient = request.env["hospital.patient"].sudo().register_portal_patient(post)
                request.env.cr.commit()
                password = post.get("password")
                uid = request.session.authenticate(request.db, user.login, password)
                if not uid:
                    return request.redirect(
                        f"/web/login?redirect=/appointment/book&login={user.login}"
                    )
                return request.redirect("/appointment/book?account_created=1")
            except (UserError, ValidationError, SignupError, ValueError) as e:
                values["error"] = str(e)
                values["post"] = post
        return request.render("smart_hospital_appointment.website_patient_register", values)


if Website:
    class HospitalWebsiteHome(Website):
        @http.route("/", auth="public", website=True, sitemap=True)
        def index(self, **kw):
            HomeContent = request.env["hospital.home.content"]
            home_contents = HomeContent.get_published_body_contents()
            if home_contents:
                return request.render(
                    "smart_hospital_appointment.hospital_homepage",
                    {
                        "home_sections": HomeContent.prepare_home_sections(home_contents),
                        "doctor_count": request.env["hospital.doctor"].sudo().search_count(
                            [("active", "=", True), ("is_unavailable", "=", False)]
                        ),
                    },
                )
            return super().index(**kw)
