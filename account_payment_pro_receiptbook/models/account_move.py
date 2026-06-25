from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    receiptbook_id = fields.Many2one(
        related="origin_payment_id.receiptbook_id",
        store=True,
    )

    def _get_last_sequence_domain(self, relaxed=False):
        """para transferencias no queremos que se enumere con el ultimo numero de asiento porque podria ser un
        pago generado por un grupo de pagos y en ese caso el numero viene dado por el talonario de recibo/pago.
        Para esto creamos campo related stored a receiptbook_id de manera de que un asiento sepa si fue creado
        o no desde un payment group
        """
        if self.journal_id.type in ("cash", "bank", "credit") and not self.receiptbook_id:
            where_string, param = super(
                AccountMove, self.with_context(without_receiptbook_id=True)
            )._get_last_sequence_domain(relaxed)
            where_string += " AND receiptbook_id is Null"
        else:
            where_string, param = super(AccountMove, self)._get_last_sequence_domain(relaxed)
        return where_string, param

    @api.model
    def _search(self, domain, *args, **kwargs):
        if self.env.context.get("without_receiptbook_id"):
            domain += [("receiptbook_id", "=", False)]
        return super()._search(domain, *args, **kwargs)

    @api.depends()
    def _compute_name(self):
        super()._compute_name()
        for move in self.filtered(
            lambda x: (
                x.origin_payment_id.receiptbook_id
                and (
                    x.state == "draft"
                    or x.origin_payment_id.state == "draft"
                    or x.origin_payment_id.payment_transaction_id
                )
            )
        ):
            move.name = move.origin_payment_id.name

    @api.depends("origin_payment_id.receiptbook_id")
    def _compute_l10n_latam_document_type(self):
        receiptbook_payments = self.filtered(lambda x: x.origin_payment_id.receiptbook_id)
        super(AccountMove, self - receiptbook_payments)._compute_l10n_latam_document_type()

    def _must_check_constrains_date_sequence(self):
        # OVERRIDES sequence.mixin to skip date sequence check for receiptbook moves
        self.ensure_one()
        if self.receiptbook_id:
            return False
        return super()._must_check_constrains_date_sequence()

    def _update_sequence_made_gap(self, invalidate_current=False):
        # OVERRIDE: en el core ``made_sequence_gap`` ya no es computado; se fija
        # imperativamente acá agrupando por journal + prefijo. Los asientos de
        # talonario se numeran por receiptbook (cada uno con su ``ir.sequence``),
        # así que esa lógica journal-based da falsos positivos. Acotamos la
        # detección de huecos al receiptbook + prefijo.
        receiptbook_moves = self.filtered(lambda m: m.receiptbook_id)
        if receiptbook_moves:
            receiptbook_moves._update_receiptbook_made_sequence_gap()
        if other_moves := self - receiptbook_moves:
            super(AccountMove, other_moves)._update_sequence_made_gap(invalidate_current=invalidate_current)

    def _update_receiptbook_made_sequence_gap(self):
        """Fija ``made_sequence_gap`` según la continuidad dentro del propio
        receiptbook + prefijo (no del journal).

        Un asiento posteado hace hueco cuando falta el número inmediatamente
        anterior en el mismo receiptbook. Los no posteados que ya tomaron número
        se marcan siempre. Además de ``self`` se re-evalúa el asiento siguiente
        de cada uno, porque agregar/quitar un asiento cambia si el que sigue es
        o no un hueco.
        """
        records = self.sudo()
        AccountMove = records.env["account.move"]

        moves_to_check = records
        for (receiptbook, prefix), moves in records.grouped(lambda m: (m.receiptbook_id, m.sequence_prefix)).items():
            moves_to_check |= AccountMove.search(
                [
                    ("receiptbook_id", "=", receiptbook.id),
                    ("sequence_prefix", "=", prefix),
                    ("sequence_number", "in", [n + 1 for n in moves.mapped("sequence_number")]),
                ]
            )

        unposted = moves_to_check.filtered(lambda m: m.sequence_number != 0 and m.state != "posted")
        unposted.made_sequence_gap = True

        for (receiptbook, prefix), moves in (
            (moves_to_check - unposted).grouped(lambda m: (m.receiptbook_id, m.sequence_prefix)).items()
        ):
            existing_numbers = set(
                AccountMove.search(
                    [
                        ("receiptbook_id", "=", receiptbook.id),
                        ("sequence_prefix", "=", prefix),
                        ("sequence_number", ">=", min(moves.mapped("sequence_number")) - 1),
                        ("sequence_number", "<=", max(moves.mapped("sequence_number")) - 1),
                    ]
                ).mapped("sequence_number")
            )
            for move in moves:
                move.made_sequence_gap = move.sequence_number > 1 and (move.sequence_number - 1) not in existing_numbers
