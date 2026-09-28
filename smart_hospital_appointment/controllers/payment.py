# -*- coding: utf-8 -*-

from odoo import Command, _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.portal import PaymentPortal


class HospitalAppointmentPayment(PaymentPortal):

    def _get_payable_appointment(self, appointment_id):
        appointment = request.env["hospital.appointment"].browse(appointment_id)
        if not appointment.exists() or appointment.patient_id != request.env.user.partner_id:
            raise AccessError(_("You cannot access this appointment."))
        return appointment

    def _get_appointment_payment_values(self, appointment):
        partner_sudo = request.env.user.partner_id
        company = request.env.company
        amount = appointment.amount_total
        currency = appointment.currency_id

        providers_sudo = request.env["payment.provider"].sudo()._get_compatible_providers(
            company.id, partner_sudo.id, amount, currency_id=currency.id
        )
        payment_methods_sudo = request.env["payment.method"].sudo()._get_compatible_payment_methods(
            providers_sudo.ids, partner_sudo.id, currency_id=currency.id
        )
        tokens_sudo = request.env["payment.token"].sudo()._get_available_tokens(
            providers_sudo.ids, partner_sudo.id
        )
        return {
            "company_mismatch": not self._can_partner_pay_in_company(partner_sudo, company),
            "expected_company": company,
            "show_tokenize_input_mapping": self._compute_show_tokenize_input_mapping(providers_sudo),
            "amount": amount,
            "currency": currency,
            "partner_id": partner_sudo.id,
            "providers_sudo": providers_sudo,
            "payment_methods_sudo": payment_methods_sudo,
            "tokens_sudo": tokens_sudo,
            "transaction_route": f"/my/hospital/appointment/{appointment.id}/transaction",
            "landing_route": f"/my/hospital/appointment/{appointment.id}",
            "access_token": payment_utils.generate_access_token(
                partner_sudo.id, amount, currency.id
            ),
        }

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/pay"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_hospital_appointment_pay(self, appointment_id, **kw):
        try:
            appointment = self._get_payable_appointment(appointment_id)
        except AccessError:
            return request.redirect("/my/hospital")
        if not appointment._has_to_be_paid():
            return request.redirect(f"/my/hospital/appointment/{appointment_id}")

        values = self._prepare_portal_layout_values()
        values.update(
            {
                "page_name": "hospital_pay",
                "appointment": appointment,
                "default_url": "/my/hospital",
                **self._get_appointment_payment_values(appointment),
            }
        )
        return request.render("smart_hospital_appointment.portal_hospital_appointment_pay", values)

    @http.route(
        ["/my/hospital/appointment/<int:appointment_id>/transaction"],
        type="json",
        auth="user",
    )
    def portal_hospital_appointment_transaction(self, appointment_id, access_token=None, **kwargs):
        try:
            appointment = self._get_payable_appointment(appointment_id)
        except AccessError:
            raise ValidationError(_("You cannot pay for this appointment."))
        if not appointment._has_to_be_paid():
            raise ValidationError(_("This appointment does not require a payment."))

        partner_sudo = request.env.user.partner_id
        amount = appointment.amount_total
        currency = appointment.currency_id
        if not payment_utils.check_access_token(access_token, partner_sudo.id, amount, currency.id):
            raise ValidationError(_("The access token is invalid."))

        self._validate_transaction_kwargs(kwargs)
        kwargs.update(
            {
                "amount": amount,
                "currency_id": currency.id,
                "partner_id": partner_sudo.id,
            }
        )
        tx_sudo = self._create_transaction(
            custom_create_values={"hospital_appointment_ids": [Command.set([appointment.id])]},
            **kwargs,
        )
        return tx_sudo._get_processing_values()
