from odoo import fields, models


class HospitalSpecialization(models.Model):
    _name = "hospital.specialization"
    _description = "Hospital Specialization"
    _order = "name"

    name = fields.Char(required=True)
