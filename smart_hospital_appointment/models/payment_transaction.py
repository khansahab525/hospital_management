from odoo import SUPERUSER_ID, api, fields, models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    hospital_appointment_ids = fields.Many2many(
        "hospital.appointment",
        "hospital_appointment_transaction_rel",
        "transaction_id",
        "appointment_id",
        string="Hospital Appointments",
        copy=False,
        readonly=True,
    )

    @api.model
    def _compute_reference_prefix(self, provider_code, separator, **values):
        command_list = values.get("hospital_appointment_ids")
        if command_list:
            appointment_ids = self._fields["hospital_appointment_ids"].convert_to_cache(
                command_list, self
            )
            appointments = self.env["hospital.appointment"].sudo().browse(appointment_ids).exists()
            if len(appointments) == len(appointment_ids):
                return separator.join(appointments.mapped("name"))
        return super()._compute_reference_prefix(provider_code, separator, **values)

    def _log_message_on_linked_documents(self, message):
        super()._log_message_on_linked_documents(message)
        if self.env.uid == SUPERUSER_ID or self.env.context.get("payment_backend_action"):
            author = self.env.user.partner_id
        else:
            author = self.partner_id
        appointments = self.hospital_appointment_ids or self.source_transaction_id.hospital_appointment_ids
        for appointment in appointments.sudo():
            appointment.message_post(body=message, author_id=author.id)
