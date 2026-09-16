from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _search_get_details(self, search_type, order, options):
        result = super()._search_get_details(search_type, order, options)
        if search_type in ("doctors", "all"):
            result.append(self.env["hospital.doctor"]._search_get_detail(self, order, options))
        if search_type in ("specializations", "all"):
            result.append(
                self.env["hospital.specialization"]._search_get_detail(self, order, options)
            )
        return result
