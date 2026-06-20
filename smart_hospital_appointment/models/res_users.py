from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    branch_id = fields.Many2one(
        "hospital.branch",
        string="Current Branch",
        domain="[('id', 'in', allowed_branch_ids)]",
        help="Default active branch for this user.",
    )
    allowed_branch_ids = fields.Many2many(
        "hospital.branch",
        "res_users_hospital_branch_rel",
        "user_id",
        "branch_id",
        string="Allowed Branches",
        help="Branches this user can access and switch between.",
    )

    @api.constrains("branch_id", "allowed_branch_ids")
    def _check_branch_access(self):
        for user in self:
            if user.branch_id and user.branch_id not in user.allowed_branch_ids:
                raise ValidationError(
                    "The current branch must be one of the user's allowed branches."
                )

    @api.onchange("allowed_branch_ids")
    def _onchange_allowed_branch_ids(self):
        if self.branch_id and self.branch_id not in self.allowed_branch_ids:
            self.branch_id = self.allowed_branch_ids[:1]
        elif not self.branch_id and self.allowed_branch_ids:
            self.branch_id = self.allowed_branch_ids[:1]

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._sync_hospital_branch_access()
        return users

    def write(self, vals):
        res = super().write(vals)
        if "branch_id" in vals:
            self.env.registry.clear_cache()
        if not self.env.context.get("skip_hospital_branch_sync") and (
            "allowed_branch_ids" in vals or "branch_id" in vals or "groups_id" in vals
        ):
            self._sync_hospital_branch_access()
        return res

    def _is_hospital_admin(self):
        self.ensure_one()
        return self.has_group("base.group_system") or self.has_group(
            "smart_hospital_appointment.group_hospital_admin"
        )

    def _is_hospital_receptionist(self):
        self.ensure_one()
        return self.has_group("smart_hospital_appointment.group_hospital_receptionist")

    def _is_hospital_doctor(self):
        self.ensure_one()
        return self.has_group("smart_hospital_appointment.group_hospital_doctor")

    def _is_hospital_doctor_only(self):
        self.ensure_one()
        return (
            self._is_hospital_doctor()
            and not self._is_hospital_admin()
            and not self._is_hospital_receptionist()
        )

    def _get_hospital_doctor_rule_context(self):
        self.ensure_one()
        doctor = self.env["hospital.doctor"].sudo().search(
            [("user_id", "=", self.id)], limit=1
        )
        patient_partner_ids = []
        if doctor:
            patient_partner_ids = (
                self.env["hospital.appointment"]
                .sudo()
                .search([("doctor_id", "=", doctor.id)])
                .mapped("patient_id")
                .ids
            )
        return {
            "hospital_doctor_id": doctor.id if doctor else False,
            "hospital_doctor_patient_partner_ids": patient_partner_ids,
        }

    @api.model
    def _unlink_legacy_hospital_group(self, group, replacement_group=None):
        """Remove a deprecated group from users, rules, and access rights before unlink."""
        if not group or not group.exists():
            return
        Access = self.env["ir.model.access"].sudo()
        Rule = self.env["ir.rule"].sudo()

        Access.search([("group_id", "=", group.id)]).unlink()

        legacy_rules = Rule.search([("groups", "in", group.id)])
        for rule in legacy_rules:
            ops = [(3, group.id)]
            if replacement_group and replacement_group not in rule.groups:
                ops.append((4, replacement_group.id))
            rule.write({"groups": ops})

        for user in group.users:
            user.with_context(skip_hospital_branch_sync=True).write(
                {"groups_id": [(3, group.id)]}
            )

        group.unlink()

    @api.model
    def _assign_hospital_role_groups(self):
        """Migrate legacy groups and sync role assignments on module upgrade."""
        admin_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_admin", raise_if_not_found=False
        )
        receptionist_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_receptionist",
            raise_if_not_found=False,
        )
        doctor_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_doctor", raise_if_not_found=False
        )
        legacy_staff = self.env.ref(
            "smart_hospital_appointment.group_hospital_staff", raise_if_not_found=False
        )
        legacy_branch_user = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_user",
            raise_if_not_found=False,
        )
        legacy_branch_rule = self.env.ref(
            "smart_hospital_appointment.hospital_branch_user_rule",
            raise_if_not_found=False,
        )

        if legacy_staff and receptionist_group and legacy_staff != receptionist_group:
            for user in legacy_staff.users:
                ops = [(4, receptionist_group.id), (3, legacy_staff.id)]
                user.with_context(skip_hospital_branch_sync=True).write(
                    {"groups_id": ops}
                )

        if legacy_branch_rule:
            legacy_branch_rule.unlink()

        self._unlink_legacy_hospital_group(legacy_branch_user, receptionist_group)
        if legacy_staff and legacy_staff != receptionist_group:
            self._unlink_legacy_hospital_group(legacy_staff, receptionist_group)

        if not receptionist_group:
            return

        Doctor = self.env["hospital.doctor"].sudo()
        doctor_users = Doctor.search([("user_id", "!=", False)]).mapped("user_id")
        other_role_groups = [
            g
            for g in (receptionist_group, admin_group)
            if g
        ]

        for doctor_user in doctor_users:
            if not doctor_group:
                continue
            group_ops = [(4, doctor_group.id)]
            for group in other_role_groups:
                if group in doctor_user.groups_id:
                    group_ops.append((3, group.id))
            doctor_user.with_context(skip_hospital_branch_sync=True).write(
                {"groups_id": group_ops}
            )

        doctor_users._sync_hospital_branch_access()

    @api.model
    def _cleanup_hospital_branch_admin_groups(self):
        """Re-sync branch groups for all users (runs on module upgrade)."""
        self.search([("allowed_branch_ids", "!=", False)])._sync_hospital_branch_access()
        admins = self.search([("groups_id", "in", [self.env.ref("base.group_system").id])])
        limited_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_limited",
            raise_if_not_found=False,
        )
        if limited_group:
            for admin in admins:
                if limited_group in admin.groups_id:
                    super(ResUsers, admin).with_context(
                        skip_hospital_branch_sync=True
                    ).write({"groups_id": [(3, limited_group.id)]})

    def _sync_hospital_branch_access(self):
        limited_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_limited",
            raise_if_not_found=False,
        )
        legacy_branch_user = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_user",
            raise_if_not_found=False,
        )
        if not limited_group:
            return

        for user in self:
            updates = {}
            if user.allowed_branch_ids and not user.branch_id:
                updates["branch_id"] = user.allowed_branch_ids[0].id

            group_ops = []
            if legacy_branch_user and legacy_branch_user in user.groups_id:
                group_ops.append((3, legacy_branch_user.id))

            if user._is_hospital_admin() or user._is_hospital_doctor_only():
                if limited_group in user.groups_id:
                    group_ops.append((3, limited_group.id))
            elif user._is_hospital_receptionist() and user.allowed_branch_ids:
                if limited_group not in user.groups_id:
                    group_ops.append((4, limited_group.id))
            elif limited_group in user.groups_id:
                group_ops.append((3, limited_group.id))

            if group_ops:
                updates["groups_id"] = group_ops

            if updates:
                super(ResUsers, user).with_context(skip_hospital_branch_sync=True).write(
                    updates
                )

    def context_get(self):
        context = dict(super().context_get())
        user = self.env.user
        if user.allowed_branch_ids:
            context["allowed_branch_ids"] = user.allowed_branch_ids.ids
        if user.branch_id:
            context["hospital_branch_id"] = user.branch_id.id
        return context
