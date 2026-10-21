# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestReceiptDebtLegalEntity(AccountTestInvoicingCommon):
    """El recibo lista la deuda según el tilde de bloqueo de la raíz del árbol.

    Con stores toda la deuda vivía en una sola compañía y el recibo la listaba entera.
    Branches parte la compañía, y el recibo se partía con ella: un cliente compra en una
    sucursal, va a pagar a otra y el operador lo ve sin deuda.

    Según "Block Inter-Company Reconciliation" de la raíz, el recibo lista la deuda de todo
    el árbol (sin bloqueo), la de la entidad fiscal (bloqueo entre entidades distintas) o
    solo la de la compañía del pago (bloqueo siempre), aunque el usuario no tenga
    seleccionadas las otras compañías. En todos los casos el pago queda en la compañía
    donde se hizo.
    """

    PARENT_VAT = "30111111118"
    OTHER_VAT = "30222222226"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.company_data["company"]
        cls.parent_invoice = cls.init_invoice("out_invoice", amounts=[100.0], post=True, company=cls.parent)
        cls.partner = cls.parent_invoice.partner_id

        cls.parent.country_id = False
        cls.parent.vat = cls.PARENT_VAT
        cls.same_entity = cls.env["res.company"].create(
            {"name": "Sucursal mismo CUIT", "parent_id": cls.parent.id, "vat": cls.PARENT_VAT}
        )
        cls.other_entity = cls.env["res.company"].create(
            {"name": "Sucursal otro CUIT", "parent_id": cls.parent.id, "vat": cls.OTHER_VAT}
        )
        cls.income = cls.env["account.account"].search(
            [("company_ids", "in", cls.parent.id), ("account_type", "=", "income")], limit=1
        )
        # Cuenta corriente propia en cada sucursal, que es el escenario de cuentas
        # corrientes independientes por sucursal, y una factura abierta en cada una.
        cls.same_entity_invoice = cls._invoice_in_branch(cls.same_entity, "01")
        cls.other_entity_invoice = cls._invoice_in_branch(cls.other_entity, "02")

    @classmethod
    def _invoice_in_branch(cls, company, suffix):
        receivable = cls.env["account.account"].create(
            {
                "name": "Deudores %s" % company.name,
                "code": "ZZ%s" % suffix,
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.set(company.ids)],
            }
        )
        cls.partner.with_company(company).property_account_receivable_id = receivable
        journal = cls.env["account.journal"].create(
            {"name": "Ventas %s" % company.name, "code": "ZV%s" % suffix, "type": "sale", "company_id": company.id}
        )
        invoice = (
            cls.env["account.move"]
            .with_company(company)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": cls.partner.id,
                    "journal_id": journal.id,
                    "company_id": company.id,
                    "invoice_line_ids": [
                        Command.create(
                            {"name": "x", "quantity": 1, "price_unit": 100, "tax_ids": [], "account_id": cls.income.id}
                        )
                    ],
                }
            )
        )
        invoice.action_post()
        return invoice

    def _debt_listed(self, company, selected):
        payment = (
            self.env["account.payment"]
            .with_context(allowed_company_ids=selected.ids)
            .new(
                {
                    "partner_id": self.partner.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "company_id": company.id,
                }
            )
        )
        return self.env["account.move.line"].search(payment._get_to_pay_move_lines_domain())

    def test_without_the_block_the_receipt_lists_the_debt_of_the_whole_tree(self):
        """Lo que se había perdido: desde la sucursal se ve la deuda del resto, sin seleccionarlo."""
        listed = self._debt_listed(self.same_entity, self.same_entity)

        self.assertEqual(listed.company_id, self.parent + self.same_entity + self.other_entity)

    def test_with_the_block_the_receipt_lists_only_its_company(self):
        """Si no se concilia entre compañías, el recibo no ofrece deuda de otras, ni tildándolas."""
        self.parent.block_intercompany_conciliation = "all"
        every_company = self.parent + self.same_entity + self.other_entity

        self.assertEqual(self._debt_listed(self.same_entity, every_company).company_id, self.same_entity)
        self.assertEqual(self._debt_listed(self.parent, every_company).company_id, self.parent)

    def test_blocked_between_legal_entities_lists_the_legal_entity(self):
        """Solo la entidad fiscal, aunque el usuario no tenga seleccionada la otra compañía."""
        self.parent.block_intercompany_conciliation = "other_legal_entity"

        self.assertEqual(
            self._debt_listed(self.same_entity, self.same_entity).company_id, self.parent + self.same_entity
        )
        self.assertEqual(self._debt_listed(self.other_entity, self.other_entity).company_id, self.other_entity)

    def test_add_all_takes_the_debt_of_several_companies(self):
        """Antes, "Add All" con deuda en dos compañías rechazaba el pago por "different companies"."""
        journal = self.env["account.journal"].create(
            {"name": "Banco sucursal", "code": "ZZC", "type": "bank", "company_id": self.same_entity.id}
        )
        payment = (
            self.env["account.payment"]
            .with_context(allowed_company_ids=self.same_entity.ids)
            .create(
                {
                    "partner_id": self.partner.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "company_id": self.same_entity.id,
                    "journal_id": journal.id,
                    "amount": 100.0,
                }
            )
        )

        payment.action_add_all()

        self.assertEqual(payment.to_pay_move_line_ids.company_id, self.parent + self.same_entity + self.other_entity)

    def test_the_payment_keeps_the_company_where_it_was_made(self):
        """Aunque pague deuda de otra sucursal de la entidad, el pago es de esa compañía.

        Es lo que el ``_check_company_domain`` de ``account.move.line`` en ``account_ux``
        habilita: sin eso, el m2m rechazaría el apunte del padre y este create fallaría.
        """
        parent_debt = self.parent_invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        journal = self.env["account.journal"].create(
            {"name": "Banco sucursal", "code": "ZZB", "type": "bank", "company_id": self.same_entity.id}
        )

        payment = (
            self.env["account.payment"]
            .with_context(allowed_company_ids=(self.parent + self.same_entity).ids)
            .create(
                {
                    "partner_id": self.partner.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "company_id": self.same_entity.id,
                    "journal_id": journal.id,
                    "amount": 100.0,
                    "to_pay_move_line_ids": [Command.set(parent_debt.ids)],
                }
            )
        )

        self.assertEqual(payment.company_id, self.same_entity)
        self.assertEqual(payment.to_pay_move_line_ids.company_id, self.parent)
