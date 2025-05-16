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
        o no desde unpaymetn group
        TODO: tal vez lo mejor sea cambiar para no guardar mas numero de recibo en el asiento, pero eso es un cambio
        gigante
        """
        if self.journal_id.type in ("cash", "bank") and not self.receiptbook_id:
            # mandamos en contexto que estamos en esta condicion para poder meternos en el search que ejecuta super
            # y que el pago de referencia que se usa para adivinar el tipo de secuencia sea un pago sin tipo de
            # documento
            where_string, param = super(
                AccountMove, self.with_context(without_receiptbook_id=True)
            )._get_last_sequence_domain(relaxed)
            where_string += " AND receiptbook_id is Null"
        else:
            where_string, param = super(AccountMove, self)._get_last_sequence_domain(relaxed)
        return where_string, param

    @api.model
    def _search(self, domain, *args, **kwargs):
        if self._context.get("without_receiptbook_id"):
            domain += [("receiptbook_id", "=", False)]
        return super()._search(domain, *args, **kwargs)

    def _compute_made_sequence_hole(self):
        receiptbook_recs = self.filtered(lambda x: x.receiptbook_id and x.journal_id.type in ("bank", "cash"))
        receiptbook_recs.made_sequence_hole = False
        super(AccountMove, self - receiptbook_recs)._compute_made_sequence_hole()

    @api.depends()
    def _compute_name(self):
        super()._compute_name()
        for move in self.filtered(
            lambda x: x.origin_payment_id.receiptbook_id
            and (x.state == "draft" or x.origin_payment_id.state == "draft")
        ):
            move.name = move.origin_payment_id.name

    @api.depends("origin_payment_id.receiptbook_id")
    def _compute_l10n_latam_document_type(self):
        receiptbook_payments = self.filtered(lambda x: x.origin_payment_id.receiptbook_id)
        super(AccountMove, self - receiptbook_payments)._compute_l10n_latam_document_type()

    @api.depends()
    def _compute_made_sequence_gap(self):
        with_receiptbook = self.filtered(lambda move: move.receiptbook_id)
        unposted_recceiptbook = with_receiptbook.filtered(
            lambda move: move.sequence_number != 0 and move.state != "posted"
        )
        unposted_recceiptbook.made_sequence_gap = True

        for (receiptbook, prefix), moves in (
            (with_receiptbook - unposted_recceiptbook).grouped(lambda m: (m.receiptbook_id, m.sequence_prefix)).items()
        ):
            previous_numbers = set(
                self.env["account.move"]
                .sudo()
                .search(
                    [
                        ("receiptbook_id", "=", receiptbook.id),
                        ("sequence_prefix", "=", prefix),
                        ("sequence_number", ">=", min(moves.mapped("sequence_number")) - 1),
                        ("sequence_number", "<=", max(moves.mapped("sequence_number")) - 1),
                    ]
                )
                .mapped("sequence_number")
            )
            for move in moves:
                move.made_sequence_gap = move.sequence_number > 1 and (move.sequence_number - 1) not in previous_numbers

        super(AccountMove, self - with_receiptbook)._compute_made_sequence_gap()
