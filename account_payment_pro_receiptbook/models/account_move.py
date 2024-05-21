from odoo import models, api, fields, _


class AccountMove(models.Model):
    _inherit = "account.move"

    receiptbook_id = fields.Many2one(
        related='payment_id.receiptbook_id',
        store=True,
    )

    def _get_last_sequence_domain(self, relaxed=False):
        """ para transferencias no queremos que se enumere con el ultimo numero de asiento porque podria ser un
        pago generado por un grupo de pagos y en ese caso el numero viene dado por el talonario de recibo/pago.
        Para esto creamos campo related stored a receiptbook_id de manera de que un asiento sepa si fue creado
        o no desde unpaymetn group
        TODO: tal vez lo mejor sea cambiar para no guardar mas numero de recibo en el asiento, pero eso es un cambio
        gigante
        """
        if self.journal_id.type in ('cash', 'bank') and not self.receiptbook_id:
            # mandamos en contexto que estamos en esta condicion para poder meternos en el search que ejecuta super
            # y que el pago de referencia que se usa para adivinar el tipo de secuencia sea un pago sin tipo de
            # documento
            where_string, param = super(
                AccountMove, self.with_context(without_receiptbook_id=True))._get_last_sequence_domain(relaxed)
            where_string += " AND receiptbook_id is Null"
        else:
            where_string, param = super(AccountMove, self)._get_last_sequence_domain(relaxed)
        return where_string, param

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        if self._context.get('without_receiptbook_id'):
            domain += [('receiptbook_id', '=', False)]
        return super()._search(domain, offset=offset, limit=limit, order=order, access_rights_uid=access_rights_uid)

    def _compute_made_sequence_hole(self):
        receiptbook_recs = self.filtered(lambda x: x.receiptbook_id and x.journal_id.type in ('bank', 'cash'))
        receiptbook_recs.made_sequence_hole = False
        super(AccountMove, self - receiptbook_recs)._compute_made_sequence_hole()
