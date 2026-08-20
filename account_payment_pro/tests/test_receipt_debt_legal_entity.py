# © ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestReceiptDebtLegalEntity(AccountTestInvoicingCommon):
    """El recibo lista la deuda de toda la entidad fiscal, acotada a lo seleccionado.

    Con stores toda la deuda vivía en una sola compañía y el recibo la listaba entera.
    Branches parte la compañía, y el recibo se partía con ella: filtraba por la compañía
    del pago, así que una sucursal no veía la deuda de su padre ni al revés, sin ningún
    aviso — el operador veía al cliente sin deuda.

    Ahora el filtro es la entidad fiscal intersecada con las compañías que el usuario
    tiene seleccionadas, y el pago sigue quedando en la compañía donde se hizo.
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

    def test_the_receipt_lists_the_debt_of_the_whole_legal_entity(self):
        """Desde la sucursal se ve la deuda del padre, que es lo que se había perdido."""
        every_company = self.parent + self.same_entity + self.other_entity

        listed = self._debt_listed(self.same_entity, every_company)

        self.assertEqual(listed.company_id, self.parent + self.same_entity)

    def test_it_lists_the_same_debt_from_the_parent(self):
        """Y al revés: la padre cobra la deuda de su sucursal."""
        every_company = self.parent + self.same_entity + self.other_entity

        listed = self._debt_listed(self.parent, every_company)

        self.assertEqual(listed.company_id, self.parent + self.same_entity)

    def test_the_debt_of_another_legal_entity_is_never_listed(self):
        """La garantía que se conserva: otra entidad fiscal no entra ni tildándola."""
        every_company = self.parent + self.same_entity + self.other_entity

        listed = self._debt_listed(self.parent, every_company)

        self.assertNotIn(self.other_entity, listed.company_id)

    def test_a_company_the_user_did_not_select_is_not_listed(self):
        """ "Ni más ni menos que las seleccionadas": sin tildar la sucursal, su deuda no va."""
        listed = self._debt_listed(self.parent, self.parent)

        self.assertEqual(listed.company_id, self.parent)

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
