from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        session_info = super().session_info()
        user = self.env.user
        if session_info.get("is_internal_user") and user.allowed_branch_ids:
            session_info["user_branches"] = {
                "current_branch": user.branch_id.id if user.branch_id else False,
                "allowed_branches": {
                    branch.id: {
                        "id": branch.id,
                        "name": branch.name,
                        "code": branch.code,
                    }
                    for branch in user.allowed_branch_ids
                },
            }
            session_info["display_switch_branch_menu"] = len(user.allowed_branch_ids) > 1
        else:
            session_info["user_branches"] = {
                "current_branch": False,
                "allowed_branches": {},
            }
            session_info["display_switch_branch_menu"] = False
        return session_info
