from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HospitalPatient(models.Model):
    _name = "hospital.patient"
    _description = "Hospital Patient"
    _inherit = ["hospital.branch.filtered", "mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    patient_code = fields.Char(
        string="Patient ID", readonly=True, default=lambda self: "New", copy=False
    )
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    user_id = fields.Many2one(
        "res.users",
        string="Registered By",
        default=lambda self: self.env.uid,
        ondelete="set null",
        help="Staff user who registered this patient.",
    )
    age = fields.Integer(required=True)
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("other", "Other")], required=True
    )
    phone = fields.Char(required=True)
    email = fields.Char()
    address = fields.Text()
    medical_history = fields.Html()
    allergies = fields.Text()
    branch_id = fields.Many2one(
        "hospital.branch",
        required=True,
        tracking=True,
        default=lambda self: self.env.context.get("hospital_branch_id")
        or (self.env.user.branch_id.id if self.env.user.branch_id else False),
    )
    appointment_count = fields.Integer(compute="_compute_appointment_count")

    _sql_constraints = [
        ("hospital_patient_code_uniq", "unique(patient_code)", "Patient ID must be unique."),
    ]

    @api.depends("partner_id")
    def _compute_appointment_count(self):
        Appointment = self.env["hospital.appointment"]
        for rec in self:
            if rec.partner_id:
                rec.appointment_count = Appointment.search_count([("patient_id", "=", rec.partner_id.id)])
            else:
                rec.appointment_count = 0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        user = self.env.user
        if "branch_id" in fields_list and not res.get("branch_id"):
            branch_id = self.env.context.get("hospital_branch_id") or user.branch_id.id
            if branch_id:
                res["branch_id"] = branch_id
        if "user_id" in fields_list and not res.get("user_id"):
            res["user_id"] = user.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"].sudo()
        user = self.env.user
        default_branch = self.env.context.get("hospital_branch_id") or user.branch_id.id
        for vals in vals_list:
            if vals.get("patient_code", "New") == "New":
                vals["patient_code"] = seq.next_by_code("hospital.patient") or "New"
            if not vals.get("branch_id") and default_branch:
                vals["branch_id"] = default_branch
            if not vals.get("user_id"):
                vals["user_id"] = user.id
        return super().create(vals_list)

    @api.model
    def register_portal_patient(self, data):
        """Create a portal user and linked patient record from website registration."""
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or ""
        phone = (data.get("phone") or "").strip()
        gender = data.get("gender")
        address = (data.get("address") or "").strip()
        branch_id = int(data.get("branch_id") or 0)
        try:
            age = int(data.get("age") or 0)
        except (TypeError, ValueError):
            age = 0

        if not name:
            raise UserError(_("Please enter your full name."))
        if not email:
            raise UserError(_("Please enter your email address."))
        if not password:
            raise UserError(_("Please enter a password."))
        if password != confirm_password:
            raise UserError(_("Passwords do not match. Please retype them."))
        if len(password) < 8:
            raise UserError(_("Password must be at least 8 characters."))
        if not phone:
            raise UserError(_("Please enter your phone number."))
        if age <= 0:
            raise UserError(_("Please enter a valid age."))
        if gender not in ("male", "female", "other"):
            raise UserError(_("Please select your gender."))
        branch = self.env["hospital.branch"].sudo().browse(branch_id)
        if not branch.exists() or not branch.active:
            raise UserError(_("Please select a valid hospital branch."))

        Users = self.env["res.users"].sudo()
        if Users.search([("login", "=", email)], limit=1):
            raise UserError(_("An account with this email already exists. Please sign in instead."))
        if self.sudo().search([("email", "=", email)], limit=1):
            raise UserError(_("A patient record with this email already exists."))

        user_vals = {
            "name": name,
            "login": email,
            "email": email,
            "password": password,
            "phone": phone,
            "branch_id": branch.id,
            "allowed_branch_ids": [(6, 0, [branch.id])],
        }
        user = Users.with_context(no_reset_password=True)._create_user_from_template(user_vals)
        partner = user.partner_id
        partner.sudo().write(
            {
                "name": name,
                "email": email,
                "phone": phone,
                "street": address or False,
            }
        )
        patient = self.sudo().create(
            {
                "name": name,
                "partner_id": partner.id,
                "user_id": user.id,
                "age": age,
                "gender": gender,
                "phone": phone,
                "email": email,
                "address": address or False,
                "branch_id": branch.id,
            }
        )
        return user, patient
