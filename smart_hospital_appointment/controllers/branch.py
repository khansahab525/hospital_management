# -*- coding: utf-8 -*-

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class HospitalBranchController(http.Controller):
    @http.route("/smart_hospital/switch_branch", type="json", auth="user")
    def switch_branch(self, branch_id):
        user = request.env.user
        branch = request.env["hospital.branch"].browse(int(branch_id))
        if not branch.exists() or branch not in user.allowed_branch_ids:
            raise AccessError("You are not allowed to switch to this branch.")
        user.sudo().write({"branch_id": branch.id})
        request.env.registry.clear_cache()
        return {"branch_id": branch.id, "branch_name": branch.name}
