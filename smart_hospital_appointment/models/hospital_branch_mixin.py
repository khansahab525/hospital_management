from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.osv import expression


class HospitalBranchFiltered(models.AbstractModel):
    _name = "hospital.branch.filtered"
    _description = "Hospital Current Branch Filter"

    @api.model
    def _get_hospital_branch_search_domain(self):
        user = self.env.user
        if self.env.su or not user.allowed_branch_ids or not user.branch_id:
            return []
        field_name = getattr(self, "_hospital_branch_field", "branch_id")
        if field_name == "branch_ids":
            return [(field_name, "in", user.branch_id.id)]
        return [(field_name, "=", user.branch_id.id)]

    def _check_hospital_branch_access(self):
        branch_domain = self._get_hospital_branch_search_domain()
        if not branch_domain:
            return
        invalid = self - self.filtered_domain(branch_domain)
        if invalid:
            raise AccessError(
                _("You can only access records from your current branch (%s).")
                % self.env.user.branch_id.display_name
            )

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
