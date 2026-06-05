from odoo import api, models


class IrRule(models.Model):
    _inherit = "ir.rule"

    def _compute_domain_keys(self):
        return super()._compute_domain_keys() + ["hospital_branch_id"]

    def _eval_context(self):
        eval_context = super()._eval_context()
        branch_id = self.env.context.get("hospital_branch_id")
        if not branch_id:
            branch_id = self.env.user.sudo().branch_id.id
        eval_context["hospital_branch_id"] = branch_id
        return eval_context

    @api.model
    def _update_hospital_branch_rule_domains(self):
        rule_domains = {
            "smart_hospital_appointment.hospital_branch_user_rule": (
                "Hospital Branch: current branch only",
                "[('id', '=', hospital_branch_id)]",
            ),
            "smart_hospital_appointment.hospital_appointment_branch_rule": (
                "Hospital Appointment: current branch only",
                "[('branch_id', '=', hospital_branch_id)]",
            ),
            "smart_hospital_appointment.hospital_patient_branch_rule": (
                "Hospital Patient: current branch only",
                "[('branch_id', '=', hospital_branch_id)]",
            ),
            "smart_hospital_appointment.hospital_doctor_branch_rule": (
                "Hospital Doctor: current branch only",
                "[('branch_ids', 'in', hospital_branch_id)]",
            ),
            "smart_hospital_appointment.hospital_doctor_availability_branch_rule": (
                "Hospital Doctor Availability: current branch only",
                "[('branch_id', '=', hospital_branch_id)]",
            ),
            "smart_hospital_appointment.hospital_appointment_medicine_line_branch_rule": (
                "Hospital Appointment Medicine Line: current branch only",
                "[('appointment_id.branch_id', '=', hospital_branch_id)]",
            ),
        }
        for xmlid, (name, domain) in rule_domains.items():
            rule = self.env.ref(xmlid, raise_if_not_found=False)
            if rule:
                rule.write({"name": name, "domain_force": domain})
        self.env.registry.clear_cache()
