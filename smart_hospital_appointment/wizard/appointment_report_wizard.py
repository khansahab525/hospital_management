import base64
from io import BytesIO

import xlsxwriter

from odoo import fields, models


class AppointmentReportWizard(models.TransientModel):
    _name = "hospital.appointment.report.wizard"
    _description = "Appointment Report Wizard"

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    branch_id = fields.Many2one("hospital.branch")
    file_data = fields.Binary(readonly=True)
    file_name = fields.Char(readonly=True)

    def _get_appointments(self):
        self.ensure_one()
        domain = [
            ("appointment_datetime", ">=", self.date_from),
            ("appointment_datetime", "<=", self.date_to),
        ]
        if self.branch_id:
            domain.append(("branch_id", "=", self.branch_id.id))
        return self.env["hospital.appointment"].search(domain, order="appointment_datetime asc")

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("smart_hospital_appointment.action_hospital_appointment_report").report_action(
            self._get_appointments(),
            data={
                "date_from": str(self.date_from),
                "date_to": str(self.date_to),
                "branch": self.branch_id.name if self.branch_id else "All Branches",
            },
        )

    def action_export_excel(self):
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("Appointments")

        header_format = workbook.add_format({"bold": True, "bg_color": "#D9E1F2"})
        date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})

        headers = [
            "Appointment",
            "Patient",
            "Doctor",
            "Branch",
            "Date/Time",
            "State",
            "Queue",
            "Priority",
            "Estimated Wait (min)",
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        for row, appt in enumerate(self._get_appointments(), start=1):
            worksheet.write(row, 0, appt.name)
            worksheet.write(row, 1, appt.patient_id.name)
            worksheet.write(row, 2, appt.doctor_id.name)
            worksheet.write(row, 3, appt.branch_id.name)
            worksheet.write_datetime(
                row,
                4,
                fields.Datetime.to_datetime(appt.appointment_datetime),
                date_format,
            )
            worksheet.write(row, 5, dict(appt._fields["state"].selection).get(appt.state))
            worksheet.write(row, 6, appt.queue_number or 0)
            worksheet.write(row, 7, "Yes" if appt.is_high_priority else "No")
            worksheet.write(row, 8, appt.estimated_wait_minutes or 0)

        worksheet.set_column(0, 8, 20)
        workbook.close()
        output.seek(0)

        file_name = "appointment_report_%s_%s.xlsx" % (self.date_from, self.date_to)
        self.write(
            {
                "file_name": file_name,
                "file_data": base64.b64encode(output.read()),
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=hospital.appointment.report.wizard&id=%s&field=file_data&filename_field=file_name&download=true"
            % self.id,
            "target": "self",
        }
