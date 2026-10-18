from odoo import api, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @api.model
    def _hospital_set_rs_symbol_before(self):
        """Show Rs / PKR before the amount (Rs. 700.00), not after."""
        currencies = self.with_context(active_test=False).search(
            [
                "|",
                ("name", "=", "PKR"),
                ("symbol", "ilike", "rs"),
            ]
        )
        for currency in currencies:
            vals = {"position": "before"}
            if currency.name == "PKR" or (currency.symbol or "").lower().startswith("rs"):
                vals["symbol"] = "Rs."
            currency.write(vals)
