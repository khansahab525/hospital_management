from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    @api.model
    def _update_hospital_appointment_menu(self):
        self.search([("url", "=", "/appointment")]).write({"url": "/my/hospital"})

    @api.model
    def _remove_hospital_register_menu(self):
        menus = self.search([("url", "in", ["/appointment/register", "/appointments/register"])])
        xmlid_menu = self.env.ref(
            "smart_hospital_appointment.website_menu_hospital_register",
            raise_if_not_found=False,
        )
        if xmlid_menu:
            menus |= xmlid_menu
        menus.unlink()
