from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def _get_receiptbook(self, partner_type):
        self.ensure_one()
        receiptbook = self.env["account.payment.receiptbook"].search(
            [
                ("partner_type", "=", partner_type),
                ("company_id", "=", self.company_id.id),
                ("company_id.use_receiptbook", "=", True),
            ],
            limit=1,
        )
        return receiptbook

    def _init_payments(self, to_process, edit_mode=False):
        for rec in to_process:
            if rec["batch"]:
                if receiptbook := self._get_receiptbook(rec["batch"]["payment_values"]["partner_type"]):
                    name = receiptbook.with_context(ir_sequence_date=self.payment_date).sequence_id.next_by_id()
                    prefix = receiptbook.document_type_id.doc_code_prefix
                    rec["create_vals"]["name"] = ("%s %s" % (prefix, name)) if prefix else name
            rec["create_vals"]["name"] = rec["create_vals"].get("name") or "/"
        return super()._init_payments(to_process, edit_mode=edit_mode)
