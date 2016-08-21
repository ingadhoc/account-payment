# -*- coding: utf-8 -*-
from openerp import models, api


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def invoice_pay_customer(self):
        """
        If company has double validation and we are paying a supplier invoice
        from invoices, then we use normal form view and not dialog
        """
        res = super(AccountInvoice, self).invoice_pay_customer()
        if self.company_id. double_validation and self.type in (
                'in_invoice', 'in_refund'):
            context = res.get('context', {})
            actions = self.env.ref('account_voucher.action_vendor_payment')
            view = self.env.ref('account_voucher.view_vendor_payment_form')
            if not actions:
                return True
            res = actions.read()[0]
            res['context'] = context
            res['view_id'] = view.id
            res['views'] = [(view.id, 'form')]
            return res
        return res
