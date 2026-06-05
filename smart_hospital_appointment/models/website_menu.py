from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    @api.model
    def _update_hospital_appointment_menu(self):
        self.search([("url", "=", "/appointment")]).write({"url": "/my/hospital"})
