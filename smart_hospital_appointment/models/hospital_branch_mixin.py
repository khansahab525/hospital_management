from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.osv import expression


class HospitalBranchFiltered(models.AbstractModel):
    _name = "hospital.branch.filtered"
    _description = "Hospital Current Branch Filter"

    @api.model
    def _get_current_hospital_branch_id(self):
        branch_id = self.env.context.get("hospital_branch_id")
        if branch_id:
            return branch_id
        return self.env.user.branch_id.id if self.env.user.branch_id else False

    @api.model
    def _get_hospital_branch_field_name(self):
        return getattr(self, "_hospital_branch_field", "branch_id")

    @api.model
    def _branch_ids_commands_with_branch(self, commands, branch_id):
        """Ensure the user's branch is linked; handles empty or partial m2m commands."""
        if not branch_id:
            return commands
        if not commands:
            return [(6, 0, [branch_id])]
        linked_ids = set()
        for command in commands:
            if command[0] == 6:
                linked_ids.update(command[2])
            elif command[0] == 4:
                linked_ids.add(command[1])
            elif command[0] == 5:
                linked_ids.clear()
            elif command[0] == 3:
                linked_ids.discard(command[1])
        if branch_id in linked_ids:
            return commands
        return list(commands) + [(4, branch_id)]

    @api.model
    def _prepare_hospital_branch_vals(self, vals_list):
        """Default branch on create so read() after insert passes branch access."""
        if self.env.su:
            return
        user = self.env.user
        if not user.allowed_branch_ids or not user.branch_id:
            return
        branch_id = self._get_current_hospital_branch_id()
        if not branch_id:
            return
        field_name = self._get_hospital_branch_field_name()
        if field_name == "id" or "." in field_name:
            return
        for vals in vals_list:
            if field_name == "branch_ids":
                vals["branch_ids"] = self._branch_ids_commands_with_branch(
                    vals.get("branch_ids"), branch_id
                )
            elif field_name == "branch_id" and not vals.get("branch_id"):
                vals["branch_id"] = branch_id

    @api.model
    def _is_persisted_id(self, record_id):
        return isinstance(record_id, int)

    def _branch_ids_include_branch(self, user_branch):
        self.ensure_one()
        if user_branch in self.branch_ids:
            return True
        if not self._is_persisted_id(self.id):
            # During create the record is not stored yet; read pending m2m from cache.
            field = self._fields["branch_ids"]
            pending = self.env.cache.get(self, field, default=None)
            if pending is not None and user_branch.id in pending:
                return True
            return False
        if not self.branch_ids:
            field = self._fields["branch_ids"]
            self.env.cr.execute(
                f"SELECT 1 FROM {field.relation} "
                f"WHERE {field.column1} = %s AND {field.column2} = %s LIMIT 1",
                (self.id, user_branch.id),
            )
            return bool(self.env.cr.fetchone())
        return False

    def _record_matches_hospital_branch(self, user_branch):
        self.ensure_one()
        if not self._is_persisted_id(self.id):
            return True
        field_name = self._get_hospital_branch_field_name()
        if field_name == "branch_ids":
            return self._branch_ids_include_branch(user_branch)
        if "." in field_name:
            value = self
            for part in field_name.split("."):
                value = value[part]
                if not value:
                    return False
            return value == user_branch
        return self[field_name] == user_branch

    @api.model
    def _get_hospital_branch_search_domain(self):
        user = self.env.user
        if self.env.su or not user.allowed_branch_ids or not user.branch_id:
            return []
        field_name = self._get_hospital_branch_field_name()
        if field_name == "branch_ids":
            return [(field_name, "in", [user.branch_id.id])]
        return [(field_name, "=", user.branch_id.id)]

    def _check_hospital_branch_access(self):
        branch_domain = self._get_hospital_branch_search_domain()
        if not branch_domain:
            return
        # Unsaved records are still being created; branch links are not final yet.
        to_check = self.filtered(lambda rec: self._is_persisted_id(rec.id))
        if not to_check:
            return
        user_branch = self.env.user.branch_id
        invalid = to_check.filtered(
            lambda rec: not rec._record_matches_hospital_branch(user_branch)
        )
        if invalid:
            raise AccessError(
                _("You can only access records from your current branch (%s).")
                % user_branch.display_name
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.su or not self.env.user.allowed_branch_ids or not self.env.user.branch_id:
            return res
        branch_id = self._get_current_hospital_branch_id()
        if not branch_id:
            return res
        field_name = self._get_hospital_branch_field_name()
        if field_name == "id" or "." in field_name:
            return res
        if field_name == "branch_ids" and "branch_ids" in fields_list and not res.get("branch_ids"):
            res["branch_ids"] = [(6, 0, [branch_id])]
        elif field_name == "branch_id" and "branch_id" in fields_list and not res.get("branch_id"):
            res["branch_id"] = branch_id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        self._prepare_hospital_branch_vals(vals_list)
        return super().create(vals_list)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        branch_domain = self._get_hospital_branch_search_domain()
        if branch_domain:
            domain = expression.AND([branch_domain, domain or []])
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            access_rights_uid=access_rights_uid,
        )

    def read(self, fields=None, load="_classic_read"):
        self._check_hospital_branch_access()
        return super().read(fields=fields, load=load)

    def write(self, vals):
        self._check_hospital_branch_access()
        return super().write(vals)

    def unlink(self):
        self._check_hospital_branch_access()
        return super().unlink()
