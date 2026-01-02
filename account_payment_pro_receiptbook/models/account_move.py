from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    receiptbook_id = fields.Many2one(
        related="origin_payment_id.receiptbook_id",
        store=True,
    )

    def _get_last_sequence_domain(self, relaxed=False):
        self.ensure_one()
        is_payment = self.origin_payment_id or self.env.context.get("is_payment")

        if self.receiptbook_id and is_payment:
            where_string = "WHERE receiptbook_id = %(receiptbook_id)s AND name != '/'"
            param = {"receiptbook_id": self.receiptbook_id.id}
            return where_string, param
        else:
            where_string, param = super()._get_last_sequence_domain(relaxed)
            where_string += " AND receiptbook_id is Null "

        return where_string, param

    def _get_starting_sequence(self):
        if self.receiptbook_id:
            if self.receiptbook_id.document_type_id:
                return "%s %s%08d" % (
                    self.receiptbook_id.document_type_id.doc_code_prefix,
                    self.receiptbook_id.prefix,
                    self.receiptbook_id.initial_sequence - 1,
                )
            return "%s%08d" % (self.receiptbook_id.prefix, self.receiptbook_id.initial_sequence - 1)
        return super()._get_starting_sequence()

    def _get_next_sequence_format(self):
        if self.receiptbook_id:
            last_sequence = self._get_last_sequence()
            new = not last_sequence
            if new:
                last_sequence = self._get_last_sequence(relaxed=True) or self._get_starting_sequence()

            format_string, format_values = self._get_sequence_format_param(last_sequence)
            return format_string, format_values
        return super()._get_next_sequence_format()

    @api.model
    def _deduce_sequence_number_reset(self, name):
        if self.receiptbook_id:
            return "never"
        return super()._deduce_sequence_number_reset(name)

    def _compute_made_sequence_hole(self):
        with_receiptbook = self.filtered(lambda x: x.receiptbook_id and x.journal_id.type in ("bank", "cash", "credit"))
        with_receiptbook.made_sequence_hole = False
        super(AccountMove, self - with_receiptbook)._compute_made_sequence_hole()

    @api.depends()
    def _compute_name(self):
        super()._compute_name()
        for move in self.filtered(
            lambda x: x.origin_payment_id.receiptbook_id
            and (x.state == "draft" or x.origin_payment_id.payment_transaction_id)
        ):
            move.name = move.origin_payment_id.name

    @api.depends("origin_payment_id.receiptbook_id")
    def _compute_l10n_latam_document_type(self):
        with_receiptbook = self.filtered(lambda x: x.origin_payment_id.receiptbook_id)
        super(AccountMove, self - with_receiptbook)._compute_l10n_latam_document_type()

    @api.depends()
    def _compute_made_sequence_gap(self):
        use_receiptbook_moves = self.filtered(lambda m: m.receiptbook_id)
        use_receiptbook_moves.made_sequence_gap = False
        if other_moves := self - use_receiptbook_moves:
            super(AccountMove, other_moves)._compute_made_sequence_gap()

    def _must_check_constrains_date_sequence(self):
        # OVERRIDES sequence.mixin to skip date sequence check for receiptbook moves
        self.ensure_one()
        if self.receiptbook_id:
            return False
        return super()._must_check_constrains_date_sequence()

    def _set_next_made_sequence_gap(self, made_gap: bool):
        if other_moves := self.filtered(lambda m: not m.receiptbook_id):
            super(AccountMove, other_moves)._set_next_made_sequence_gap(made_gap)
