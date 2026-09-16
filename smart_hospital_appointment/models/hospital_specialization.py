from odoo import api, fields, models


class HospitalSpecialization(models.Model):
    _name = "hospital.specialization"
    _description = "Hospital Specialization"
    _inherit = ["website.searchable.mixin"]
    _order = "name"

    name = fields.Char(required=True)
    website_url = fields.Char(compute="_compute_website_url")

    def _compute_website_url(self):
        for rec in self:
            rec.website_url = f"/doctors?specialization_id={rec.id}"

    @api.model
    def _search_get_detail(self, website, order, options):
        return {
            "model": "hospital.specialization",
            "requires_sudo": True,
            "base_domain": [[]],
            "search_fields": ["name"],
            "fetch_fields": ["id", "name", "website_url"],
            "mapping": {
                "name": {"name": "name", "type": "text", "match": True},
                "website_url": {"name": "website_url", "type": "text", "truncate": False},
            },
            "icon": "fa-stethoscope",
            "order": "name asc, id desc",
        }
