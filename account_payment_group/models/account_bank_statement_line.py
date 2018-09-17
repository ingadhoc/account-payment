from odoo import models, api


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    @api.multi
    def button_cancel_reconciliation(self):
        """On statement line cancel, cancel and delete related payment group.
        We couldnt overwrite payments "unreconcile" because it is call
        with payment_to_unreconcile and payment_to_cancel and we only want to
        delete payment_to_cancel
        """
        aml_to_unbind = self.env['account.move.line']
        aml_to_cancel = self.env['account.move.line']
        payment_to_cancel = self.env['account.payment']
        for st_line in self:
            aml_to_unbind |= st_line.journal_entry_ids
            for line in st_line.journal_entry_ids:
                if st_line.move_name and line.payment_id.payment_reference \
                        == st_line.move_name:
                    # there can be several moves linked to a statement line but
                    #  maximum one created by the line itself
                    aml_to_cancel |= line
                    payment_to_cancel |= line.payment_id
        payment_groups = payment_to_cancel.mapped('payment_group_id')
        res = super(
            AccountBankStatementLine, self).button_cancel_reconciliation()
        if payment_groups:
            payment_groups.update({'state': 'draft'})
            payment_groups.unlink()
        return res
