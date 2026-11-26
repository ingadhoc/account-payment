##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user


class TestCardInstallment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.card = cls.env["account.card"].create({"name": "Test Card", "company_id": cls.company.id})
        cls.plan_one = cls.env["account.card.installment"].create(
            {
                "card_id": cls.card.id,
                "name": "1",
                "divisor": 1,
                "installment": 1,
                "surcharge_coefficient": 1.0,
            }
        )
        cls.plan_three = cls.env["account.card.installment"].create(
            {
                "card_id": cls.card.id,
                "name": "3 with surcharge",
                "divisor": 3,
                "installment": 3,
                "surcharge_coefficient": 1.06,
            }
        )

    def test_installment_amounts(self):
        """Surcharge math of an installment plan.

        Covers get_fees, get_real_total and map_installment_values, including
        the guard that avoids dividing by a zero divisor.
        """
        with self.subTest("a 6% plan charges 60 over 1000"):
            self.assertAlmostEqual(self.plan_three.get_fees(1000.0), 60.0, places=2)
        with self.subTest("the real total adds the surcharge to the amount"):
            self.assertAlmostEqual(self.plan_three.get_real_total(1000.0), 1060.0, places=2)
        with self.subTest("a plan without surcharge keeps the amount"):
            self.assertAlmostEqual(self.plan_one.get_fees(1000.0), 0.0, places=2)
            self.assertAlmostEqual(self.plan_one.get_real_total(1000.0), 1000.0, places=2)
        with self.subTest("the mapped values split the total with surcharge"):
            values = self.plan_three.map_installment_values(1000.0)
            self.assertEqual(values["id"], self.plan_three.id)
            self.assertEqual(values["name"], self.plan_three.name)
            self.assertEqual(values["divisor"], 3)
            self.assertEqual(values["installment"], 3)
            self.assertAlmostEqual(values["coefficient"], 1.06, places=2)
            self.assertAlmostEqual(values["base_amount"], 1000.0, places=2)
            self.assertAlmostEqual(values["amount"], 1060.0, places=2)
            self.assertAlmostEqual(values["fee"], 60.0, places=2)
        with self.subTest("a zero divisor does not divide by zero"):
            plan_zero = self.env["account.card.installment"].create(
                {
                    "card_id": self.card.id,
                    "name": "no divisor",
                    "divisor": 0,
                    "surcharge_coefficient": 1.06,
                }
            )
            values = plan_zero.map_installment_values(1000.0)
            self.assertEqual(values["divisor"], 0)
            self.assertAlmostEqual(values["amount"], 1060.0, places=2)
            self.assertAlmostEqual(values["fee"], 60.0, places=2)

    def test_card_installment_tree(self):
        """Plans are grouped by card.

        Covers card_installment_tree, the contract that payment_pay_way and
        sale_payment_options extend.
        """
        other_card = self.env["account.card"].create({"name": "Other Card", "company_id": self.company.id})
        other_plan = self.env["account.card.installment"].create(
            {
                "card_id": other_card.id,
                "name": "6",
                "divisor": 6,
                "installment": 6,
                "surcharge_coefficient": 1.2,
            }
        )
        tree = (self.plan_one | self.plan_three | other_plan).card_installment_tree(1000.0)
        self.assertEqual(set(tree.keys()), {self.card.id, other_card.id})
        self.assertEqual(tree[self.card.id]["name"], self.card.name)
        self.assertEqual(
            {values["id"] for values in tree[self.card.id]["installments"]},
            {self.plan_one.id, self.plan_three.id},
        )
        self.assertEqual(
            [values["id"] for values in tree[other_card.id]["installments"]],
            [other_plan.id],
        )
        self.assertAlmostEqual(tree[other_card.id]["installments"][0]["amount"], 1200.0, places=2)

    def test_divisor_constraint(self):
        """A negative divisor is rejected, zero and positive ones are allowed."""
        with self.subTest("a negative divisor is rejected"):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.env["account.card.installment"].create(
                    {"card_id": self.card.id, "name": "negative", "divisor": -1}
                )
        with self.subTest("a zero divisor is allowed"):
            plan = self.env["account.card.installment"].create(
                {"card_id": self.card.id, "name": "no divisor", "divisor": 0}
            )
            self.assertEqual(plan.divisor, 0)
        with self.subTest("a positive divisor is allowed on write"):
            self.plan_three.divisor = 12
            self.plan_three.flush_recordset()
            self.assertEqual(self.plan_three.divisor, 12)

    def test_card_multicompany_rule(self):
        """Cards and plans of another company are not visible."""
        other_company = self.env["res.company"].create({"name": "Other Company"})
        other_card = self.env["account.card"].create({"name": "Other Company Card", "company_id": other_company.id})
        other_plan = self.env["account.card.installment"].create({"card_id": other_card.id, "name": "1", "divisor": 1})
        user = new_test_user(
            self.env,
            login="card_installment_user",
            groups="base.group_user,account.group_account_invoice",
            company_id=self.company.id,
            company_ids=[Command.set([self.company.id])],
        )
        with self.subTest("only the cards of its own company are visible"):
            cards = self.env["account.card"].with_user(user).search([])
            self.assertIn(self.card, cards)
            self.assertNotIn(other_card, cards)
            plans = self.env["account.card.installment"].with_user(user).search([])
            self.assertIn(self.plan_three, plans)
            self.assertNotIn(other_plan, plans)
        with self.subTest("a card of another company cannot be changed"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                other_card.with_user(user).name = "touched"
        with self.subTest("a plan of another company cannot be changed"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                other_plan.with_user(user).divisor = 5
        with self.subTest("a card cannot be created in another company"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                self.env["account.card"].with_user(user).create({"name": "Sneaked In", "company_id": other_company.id})
        with self.subTest("a card of another company cannot be deleted"):
            # a card without plans, so a successful delete would not hit the foreign key
            empty_other_card = self.env["account.card"].create(
                {"name": "Empty Other Card", "company_id": other_company.id}
            )
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                empty_other_card.with_user(user).unlink()
        with self.subTest("a card of its own company can be changed"):
            self.card.with_user(user).name = "Renamed Card"
            self.assertEqual(self.card.name, "Renamed Card")

    def test_internal_user_only_reads(self):
        """An internal user without the invoicing group reads but does not change."""
        user = new_test_user(
            self.env,
            login="card_installment_plain_user",
            groups="base.group_user",
            company_id=self.company.id,
            company_ids=[Command.set([self.company.id])],
        )
        with self.subTest("the cards of its company are visible"):
            self.assertIn(self.card, self.env["account.card"].with_user(user).search([]))
            self.assertIn(
                self.plan_three,
                self.env["account.card.installment"].with_user(user).search([]),
            )
        with self.subTest("a card cannot be changed"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                self.card.with_user(user).name = "touched"
        with self.subTest("a plan cannot be changed"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                self.plan_three.with_user(user).divisor = 5
        with self.subTest("a card cannot be created"):
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                self.env["account.card"].with_user(user).create({"name": "Sneaked In"})
        with self.subTest("a card cannot be deleted"):
            empty_card = self.env["account.card"].create({"name": "Empty Card", "company_id": self.company.id})
            with self.assertRaises(AccessError), self.env.cr.savepoint():
                empty_card.with_user(user).unlink()
