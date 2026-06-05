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

    def _is_hospital_branch_restricted(self):
        self.ensure_one()
        return not self.has_group("base.group_system")

    def _sync_hospital_branch_access(self):
        data_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_user",
            raise_if_not_found=False,
        )
        limited_group = self.env.ref(
            "smart_hospital_appointment.group_hospital_branch_limited",
            raise_if_not_found=False,
        )
        if not data_group:
            return

        for user in self:
            updates = {}
            if user.allowed_branch_ids and not user.branch_id:
                updates["branch_id"] = user.allowed_branch_ids[0].id

            group_ops = []
            if user.allowed_branch_ids:
                if data_group not in user.groups_id:
                    group_ops.append((4, data_group.id))
                if limited_group and user._is_hospital_branch_restricted():
                    if limited_group not in user.groups_id:
                        group_ops.append((4, limited_group.id))
                elif limited_group and limited_group in user.groups_id:
                    group_ops.append((3, limited_group.id))
            else:
                if data_group in user.groups_id:
                    group_ops.append((3, data_group.id))
                if limited_group and limited_group in user.groups_id:
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
