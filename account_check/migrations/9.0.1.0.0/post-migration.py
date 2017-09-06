# -*- coding: utf-8 -*-
from openupgradelib import openupgrade
from openerp.exceptions import ValidationError
from openerp.addons.account_check.models.account_check import AccountCheck
import logging
_logger = logging.getLogger(__name__)


def issue_number_interval(self):
    """
    we disable this constraint because it is possible that in the past (v8)
    this constraint does not apply correctly
    """
    return True


AccountCheck.issue_number_interval = issue_number_interval


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    # TODO copy checks and enable
    add_operations(env)
    old_journal_ids = change_issue_journals(env)
    _logger.info('old_journal_ids %s' % old_journal_ids)

    # al final no mergeamos los third checks journals
    # old_journal_ids += change_third_journals(env)

    # NO LO HACMEOS NI CON TRY PORQUE SI NO DE ALGUNA MAENRA LUEGO NOS
    # DA ERROR AL BUSCAR LOS NEW PAYMENT METHODS CREADOS CON ESTE MODULO
    # APARENTEMENTE HACE UN ROLLBACK O ALGO ASI, LO HACEMOS EN POST SCRIPT A
    # ESTO Y LISTO
    # TODO. Improove this. if this gives an error you can comment it and
    # later delete de journals by fixing manually related remaining move and
    # move lines
    # env['account.journal'].browse(old_journal_ids).unlink()
    # try:
    #     env['account.journal'].browse(old_journal_ids).unlink()
    # except:
    #     _logger.warning('Could not delete checks journals')

    # first unlink then add third issue types because if not a checkbook
    # is created for old journals and we cant unlink them

    # al final no mergeamos los third checks journals
    # env['account.journal']._enable_third_check_on_cash_journals()
    env['account.journal']._enable_issue_check_on_bank_journals()
    # primero issue para que este lo desmarque
    _enable_third_check_method(env)
    delete_old_ir_rule(env)


def delete_old_ir_rule(env):
    # this was a rule for multicompany on checkbooks but we dont use it now
    openupgrade.logged_query(env.cr, """
        DELETE from ir_rule rr
        USING ir_model_data d where rr.id=d.res_id
        and d.model = 'ir.rule' and d.module = 'account_check'
        and d.name = 'account_checkbook_rule'
        """,)


def _change_journal(cr, old_journal_id, new_journal_id):
    tables = [
        'account_move', 'account_move_line', 'account_check',
        'account_payment', 'account_bank_statement']
    for table in tables:
        openupgrade.logged_query(cr, """
            UPDATE
                %s
            SET
                journal_id=%s
            WHERE journal_id = %s
            """ % (table, new_journal_id, old_journal_id),)


def _change_journal_issue(env, checkbook_id, new_journal_id):
    cr = env.cr
    # openupgrade.logged_query(cr, """
    #     UPDATE account_move_line aml SET journal_id = %s
    #     USING account_payment ap
    #     WHERE aml.payment_id = ap.id AND ap.checkbook_id = %s
    #     """ (new_journal_id, checkbook_id),
    # )
    openupgrade.logged_query(cr, """
        SELECT aml.id FROM account_move_line aml
        INNER JOIN account_payment as ap on aml.payment_id = ap.id
        WHERE ap.checkbook_id = %s
        """ % (checkbook_id),
    )
    move_line_ids = [i for i, in cr.fetchall()]

    # agregamos asientos de debito
    openupgrade.logged_query(cr, """
        SELECT aml.id FROM account_move_line aml
        INNER JOIN account_move as am on am.id = aml.move_id
        INNER JOIN account_check_copy as ap on am.id = ap.debit_account_move_id
        WHERE ap.checkbook_id = %s
        """ % (checkbook_id),
    )
    move_line_ids += [i for i, in cr.fetchall()]

    # agregamos asientos de rechazo
    openupgrade.logged_query(cr, """
        SELECT aml.id FROM account_move_line aml
        INNER JOIN account_move as am on am.id = aml.move_id
        INNER JOIN account_check_copy as ap
        on am.id = ap.rejection_account_move_id
        WHERE ap.checkbook_id = %s
        """ % (checkbook_id),
    )
    move_line_ids += [i for i, in cr.fetchall()]

    # agregamos asientos de cambio
    openupgrade.logged_query(cr, """
        SELECT aml.id FROM account_move_line aml
        INNER JOIN account_move as am on am.id = aml.move_id
        INNER JOIN account_check_copy as ap
            on am.id = ap.return_account_move_id
        WHERE ap.checkbook_id = %s
        """ % (checkbook_id),
    )
    move_line_ids += [i for i, in cr.fetchall()]

    # if move_line_ids:
    if move_line_ids:
        openupgrade.logged_query(cr, """
            UPDATE account_move_line aml SET journal_id = %s
            WHERE id in %s
            """, (new_journal_id, tuple(move_line_ids)))
        openupgrade.logged_query(cr, """
            UPDATE account_move am SET journal_id = %s
            WHERE am.id in (SELECT move_id FROM account_move_line aml
                WHERE aml.id in %s)
            """, (new_journal_id, tuple(move_line_ids)))

    tables = ['account_check', 'account_payment']
    # 'account_voucher' no tiene checkbook_id
    for table in tables:
        openupgrade.logged_query(cr, """
            UPDATE
                %s
            SET
                journal_id=%s
            WHERE checkbook_id = %s
            """ % (table, new_journal_id, checkbook_id),)
    openupgrade.logged_query(cr, """
        UPDATE
            account_checkbook
        SET
            journal_id=%s
        WHERE id = %s
        """ % (new_journal_id, checkbook_id),)


def change_issue_journals(env):
    cr = env.cr
    old_journal_ids = []
    for checkbook in env['account.checkbook'].search([]):
        # openupgrade.logged_query(cr, """
            # SELECT
        openupgrade.logged_query(cr, """
            SELECT
                debit_journal_id,
                next_check_number
            FROM account_checkbook
            WHERE id = %s
            """, (checkbook.id,))
        read = cr.fetchall()
        if not read:
            raise ValidationError(
                'We could not found checkbook %s' % checkbook.id)
        new_journal_id, next_check_number = read[0]

        # create sequence and update number
        checkbook._create_sequence()
        checkbook.sequence_id.number_next_actual = next_check_number

        old_journal_id = checkbook.journal_id.id
        _change_journal_issue(
            env, checkbook.id, new_journal_id)

        # si existían pagos con diario cheques pero sin cheques cargados,
        # no sabemos la chequera y no los podemos mover, entonces lo borramos
        # si estaban en borrador
        env['account.payment'].search([
            ('journal_id', '=', old_journal_id), ('check_ids', '=', False),
            ('state', '=', 'draft')]).write({'journal_id': new_journal_id})
        # borramos cheques en borrador ya que no tienen mucho sentido
        env['account.check'].search([('state', '=', 'draft')]).unlink()

        # hubo casos con pagos sin cheques en importe cero, estos estan mal
        # y no los podemos migrar correctamente
        wrong_checks = env['account.payment'].search([
            ('journal_id', '=', old_journal_id), ('check_ids', '=', False),
            # sacamos lo de monto cero por ejempo porque en cudnik usaron
            # diario cheques para pagar retencion
            # ('amount', '=', 0.0)
        ])
        # en vez de borrarlos a estos, porque el asiento podria estar
        # conciliando cosas y da error y si rompemos conciliacion va a
        # molestar, los cambiamos de diario
        move_line_ids = wrong_checks.mapped('move_line_ids').ids
        if move_line_ids:
            openupgrade.logged_query(cr, """
                UPDATE account_move_line aml SET journal_id = %s
                WHERE id in %s
                """, (new_journal_id, tuple(move_line_ids)))
            openupgrade.logged_query(cr, """
                UPDATE account_move am SET journal_id = %s
                WHERE am.id in (SELECT move_id FROM account_move_line aml
                    WHERE aml.id in %s)
                """, (new_journal_id, tuple(move_line_ids)))
        if wrong_checks:
            openupgrade.logged_query(cr, """
                UPDATE
                    account_payment
                SET
                    journal_id=%s
                WHERE id in %s
                """, (new_journal_id, tuple(wrong_checks.ids)))
        # wrong_checks.cancel()
        # wrong_checks.unlink()

        # no sabemos a que diario mandar si existe 'account_bank_statement'
        # no deberia haber statements para diario de cheques, los borramos
        openupgrade.logged_query(cr, """
            DELETE FROM account_bank_statement WHERE journal_id = %s
            """, (old_journal_id,))

        old_journal_ids.append(old_journal_id)

    # if there is a default debit account we set this as deferred account
    if old_journal_ids:
        for company in env['res.company'].search([]):
            issue_journal = env['account.journal'].search([
                ('company_id', '=', company.id),
                ('id', 'in', old_journal_ids),
                ('default_debit_account_id', '!=', False),
            ], limit=1)
            if issue_journal:
                company.deferred_check_account_id = (
                    issue_journal.default_debit_account_id.id)
    return old_journal_ids


def _enable_third_check_method(env):
    """
    Search for old payment_subtype = third_check journals and move to cash
    journals of each company
    """
    cr = env.cr
    in_third_checks = env.ref(
        'account_check.account_payment_method_received_third_check')
    out_third_checks = env.ref(
        'account_check.account_payment_method_delivered_third_check')
    for company in env['res.company'].search([]):
        openupgrade.logged_query(cr, """
            SELECT
                id
            FROM account_journal
            WHERE payment_subtype = 'third_check' AND
                type in ('cash', 'bank') AND
                company_id = %s
            """, (company.id,))
        third_journals_read = cr.fetchall()
        third_journals_ids = [x[0] for x in third_journals_read]
        for third_journal in env['account.journal'].browse(
                third_journals_ids):
            third_journal.write({
                'inbound_payment_method_ids': [
                    (6, None, [in_third_checks.id])],
                'outbound_payment_method_ids': [
                    (6, None, [out_third_checks.id])],
            })


# def change_third_journals(env):
#     """
#     viejo metodo, ahora no unificamos
#     Search for old payment_subtype = third_check journals and move to cash
#     journals of each company
#     """
#     cr = env.cr
#     old_journal_ids = []
#     for company in env['res.company'].search([]):
#         openupgrade.logged_query(cr, """
#             SELECT
#                 id
#             FROM account_journal
#             WHERE payment_subtype = 'third_check' AND
#                 type in ('cash', 'bank') AND
#                 company_id = %s
#             """, (company.id,))
#         old_third_journals_read = cr.fetchall()
#         if old_third_journals_read:
#             # default order is sequence so you should order first the journal
#             # you want to use
#             new_third_journal = env['account.journal'].search([
#                 ('company_id', '=', company.id),
#                 ('type', '=', 'cash'),
#                 '|',
#                 ('currency_id', '=', company.currency_id.id),
#                 ('currency_id', '=', False),
#             ], limit=1)
#             if not new_third_journal:
#                 raise ValidationError(
#                     'We havent found a new_third_journal for company %s' % (
#                         company.id))
#             for old_journal_id in old_third_journals_read[0]:
#                 _change_journal(cr, old_journal_id, new_third_journal.id)
#                 old_journal_ids.append(old_journal_id)
#                 # if there is a default debit account we set this as holding
#                 # account
#                 old_third_journal = env[
#                     'account.journal'].browse(old_journal_id)
#                 account = old_third_journal.default_debit_account_id
#                 if account:
#                     company.holding_check_account_id = account.id
#     return old_journal_ids


def get_payment(env, voucher_id):
    """
    Because odoo create payments with different ids done vouchers we get them
    searchin on moves
    """
    if not voucher_id:
        return False
    cr = env.cr
    openupgrade.logged_query(cr, """
        SELECT
            move_id, amount, journal_id, state, create_uid, partner_id,
            reference, name, create_date
        FROM
            account_voucher_copy
        WHERE
            id = %s
            """, (voucher_id,))
    read = cr.fetchall()
    if read:
        (move_id, amount, journal_id, state, create_uid,
            partner_id, reference, name, create_date) = read[0]
        if move_id:
            domain = [('move_id', '=', move_id), ('payment_id', '!=', False)]
            payment = env[('account.move.line')].search(domain).mapped(
                'payment_id')
        # ODOO las migra en estos estados a sipreco y cia
        # elif state in ['draft', 'cancel']:
        elif state not in ['posted', 'sent', 'reconciled']:
            domain = [
                # ('state', '=', 'draft'),
                # por compatibilidad con sipreco aunque igual a draft tmb
                # deberia estar bien
                ('state', 'not in', ('posted', 'sent', 'reconciled')),
                # ('state', '=', 'draft'),
                ('journal_id', '=', journal_id),
                ('payment_reference', '=', reference),
                ('partner_id', '=', partner_id),
                ('create_date', '=', create_date),
                ('create_uid', '=', create_uid),
                # pagos negativos se conieron a positivos
                ('amount', '=', abs(amount))]
            payment = env['account.payment'].search(domain)

            # si nos devuelve mas de uno intentamos agregar condición de name
            # no lo hacemos antes ya que en otros casos no sirve
            if len(payment) > 1 and name:
                domain.append(('name', '=', name))
                payment = env['account.payment'].search(domain)

            if len(payment) != 1:
                raise ValidationError(
                    'Se encontro mas de un payment o ninguno!!! \n'
                    '* Payments: %s\n'
                    '* Domain: %s' % (payment, domain))
        else:
            raise ValidationError(
                'Error de cheque al querer vincular con pago')
        return payment
    return False


def add_operations(env):
    """
    this new method create checks and add operations, this is because odoo
    deletes checks when deleting vouchers
    other currency is not implemented on checks so we dont take it into account
    if we need it we should convert:
        company_currency_amount or amount --> amount
        amount_currency --> company_currency_amount and amount
    and also copy currency_id value
    """
    cr = env.cr
    openupgrade.logged_query(cr, """
        SELECT
            id,
            payment_date,
            state,
            name,
            number,
            journal_id,
            voucher_id,
            bank_id,
            owner_name,
            owner_vat,
            checkbook_id,
            issue_date,
            amount,
            supplier_reject_debit_note_id,
            rejection_account_move_id,
            replacing_check_id,
            debit_account_move_id,
            third_handed_voucher_id,
            customer_reject_debit_note_id,
            deposit_account_move_id,
            return_account_move_id,
            type
        FROM account_check_copy
        ORDER BY replacing_check_id desc, id desc
        """,)
    # map con claves de ids de cheques viejos y valores de ids de cheques
    # nuevos, por ahora solo lo usamos para cheques reemplazados
    checks_map = {}
    for read in cr.fetchall():
        (
            check_id,
            payment_date,
            original_state,
            name,
            number,
            journal_id,
            voucher_id,
            bank_id,
            owner_name,
            owner_vat,
            checkbook_id,
            issue_date,
            amount,
            supplier_reject_debit_note_id,
            rejection_account_move_id,
            replacing_check_id,
            debit_account_move_id,
            third_handed_voucher_id,
            customer_reject_debit_note_id,
            deposit_account_move_id,
            return_account_move_id,
            check_type) = read

        if payment_date and payment_date < issue_date:
            payment_date = issue_date

        check_vals = {
            'name': name,
            'number': number,
            'journal_id': journal_id,
            'bank_id': bank_id,
            'owner_name': owner_name,
            'owner_vat': owner_vat,
            'checkbook_id': checkbook_id,
            'issue_date': issue_date,
            'type': check_type,
            'amount': amount,
            'payment_date': payment_date,
            # 'currency_id': currency_id,
        }
        check = env['account.check'].create(check_vals)
        checks_map[check_id] = check.id
        if check.type == 'third_check':
            payment = get_payment(env, voucher_id)
            if payment:
                # payment = env['account.payment'].browse(voucher_id)
                payment.write({
                    'check_number': check.number,
                    'check_name': check.name,
                    'check_issue_date': check.issue_date,
                    'check_payment_date': check.payment_date,
                    'check_bank_id': check.bank_id.id,
                    'check_owner_vat': check.owner_vat,
                    'check_owner_name': check.owner_name,
                    'checkbook_id': check.checkbook_id.id,
                    'check_ids': [(4, check.id, False)],
                    'payment_method_id': env.ref(
                        'account_check.'
                        'account_payment_method_received_third_check').id,
                })
                if payment.state != 'draft':
                    check._add_operation(
                        'holding', payment,
                        partner=payment.partner_id, date=payment.payment_date)

            delivery_payment = get_payment(env, third_handed_voucher_id)
            # if third_handed_voucher_id:
            #     delivery_payment = env['account.payment'].browse(
            #         third_handed_voucher_id)
            if delivery_payment:
                delivery_payment.write({
                    'check_ids': [(4, check.id, False)],
                    'payment_method_id': env.ref(
                        'account_check.'
                        'account_payment_method_delivered_third_check').id,
                })
                check._add_operation(
                    'delivered', delivery_payment,
                    partner=delivery_payment.partner_id,
                    date=delivery_payment.payment_date)
            elif deposit_account_move_id:
                deposit_account_move = env['account.move'].browse(
                    deposit_account_move_id)
                check._add_operation(
                    'deposited', deposit_account_move,
                    partner=deposit_account_move.partner_id,
                    date=deposit_account_move.date)
        elif check.type == 'issue_check':
            payment = get_payment(env, voucher_id)
            if payment:
                payment.write({
                    # we only store info of last check
                    'check_number': check.number,
                    'check_name': check.name,
                    'check_issue_date': check.issue_date,
                    'check_payment_date': check.payment_date,
                    'check_bank_id': check.bank_id.id,
                    'check_owner_vat': check.owner_vat,
                    'check_owner_name': check.owner_name,
                    'checkbook_id': check.checkbook_id.id,
                    'check_ids': [(4, check.id, False)],
                    'payment_method_id': env.ref(
                        'account_check.'
                        'account_payment_method_issue_check').id,
                })
                if payment.state != 'draft':
                    check._add_operation(
                        'handed', payment,
                        partner=payment.partner_id, date=payment.payment_date)
            if debit_account_move_id:
                debit_account_move = env['account.move'].browse(
                    debit_account_move_id)
                check._add_operation(
                    'debited', debit_account_move,
                    partner=debit_account_move.partner_id,
                    date=debit_account_move.date)

        if supplier_reject_debit_note_id:
            supplier_reject_debit_note = env['account.invoice'].browse(
                supplier_reject_debit_note_id)
            check._add_operation(
                'rejected', supplier_reject_debit_note,
                partner=supplier_reject_debit_note.partner_id,
                date=supplier_reject_debit_note.date_invoice)
        elif rejection_account_move_id:
            rejection_account_move = env['account.move'].browse(
                rejection_account_move_id)
            check._add_operation(
                'rejected', rejection_account_move,
                partner=rejection_account_move.partner_id,
                date=rejection_account_move.date)

        if customer_reject_debit_note_id:
            customer_reject_debit_note = env['account.invoice'].browse(
                customer_reject_debit_note_id)
            check._add_operation(
                'reclaimed', customer_reject_debit_note,
                partner=customer_reject_debit_note.partner_id,
                date=customer_reject_debit_note.date_invoice)
            # TODO ver si hace falta
            check.state = 'reclaimed'
        # elif rejection_account_move_id:
        #     rejection_account_move = env['account.move'].browse(
        #         rejection_account_move_id)
        #     check._add_operation(
        #         'reclaimed', rejection_account_move,
        #         partner=rejection_account_move.partner_id,
        #         date=rejection_account_move.date)

        if replacing_check_id:
            replacing_check = check.browse(
                checks_map.get(replacing_check_id, False))
            if replacing_check:
                check._add_operation(
                    'changed', replacing_check,
                    partner=replacing_check.partner_id,
                    date=replacing_check.create_date)

        if return_account_move_id:
            return_account_move = env['account.move'].browse(
                return_account_move_id)
            check._add_operation(
                'returned', return_account_move,
                partner=return_account_move.partner_id,
                date=return_account_move.date)
        if original_state != check.state:
            # if check is reclaimed it was rejected in old check module
            if check.state == 'reclaimed' and original_state == 'rejected':
                continue
            # if check is delivered it was handed in old check module
            elif check.state == 'delivered' and original_state == 'handed':
                continue
            # if original_state == 'cancel' now it is draft because payments
            # dont have cancel state
            elif original_state == 'cancel' and check.state == 'draft':
                # continue
                # on new version checks are deleted when payment goes to draft
                # we cant get link and data because we dont have account move
                check.unlink()
                continue
            raise ValidationError(
                'On check %s (id: %s) check state (%s) differs from original '
                'check state (%s)' % (
                    check.name, check.id, check.state, original_state))

# old method that requires account.check to exists
# def add_operations(env):
#     cr = env.cr
#     for check in env['account.check'].search([]):
#         openupgrade.logged_query(cr, """
#             SELECT
#                 state,
#                 voucher_id,
#                 company_currency_amount,
#                 supplier_reject_debit_note_id,
#                 rejection_account_move_id,
#                 replacing_check_id,
#                 debit_account_move_id,
#                 third_handed_voucher_id,
#                 customer_reject_debit_note_id,
#                 deposit_account_move_id,
#                 return_account_move_id
#             FROM account_check
#             WHERE id = %s
#             """, (check.id,))
#         read = cr.fetchall()
#         if not read:
#             raise ValidationError('We could not found check %s' % check.id)
#         (
#             original_state,
#             voucher_id,
#             company_currency_amount,
#             supplier_reject_debit_note_id,
#             rejection_account_move_id,
#             replacing_check_id,
#             debit_account_move_id,
#             third_handed_voucher_id,
#             customer_reject_debit_note_id,
#             deposit_account_move_id,
#             return_account_move_id) = read[0]

#         if company_currency_amount:
#             check.amount_currency = check.amount
#             check.amount = company_currency_amount
#             # check.currency_id = company_currency_amount

#         if check.type == 'third_check':
#             if voucher_id:
#                 payment = env['account.payment'].browse(voucher_id)
#                 check._add_operation(
#                     'holding', payment,
#                     partner=payment.partner_id, date=payment.payment_date)

#             if third_handed_voucher_id:
#                 delivery_payment = env['account.payment'].browse(
#                     third_handed_voucher_id)
#                 check._add_operation(
#                     'delivered', delivery_payment,
#                     partner=delivery_payment.partner_id,
#                     date=delivery_payment.payment_date)
#             elif deposit_account_move_id:
#                 deposit_account_move = env['account.move'].browse(
#                     deposit_account_move_id)
#                 check._add_operation(
#                     'deposited', deposit_account_move,
#                     partner=deposit_account_move.partner_id,
#                     date=deposit_account_move.date)
#         elif check.type == 'issue_check':
#             if voucher_id:
#                 payment = env['account.payment'].browse(voucher_id)
#                 check._add_operation(
#                     'handed', payment,
#                     partner=payment.partner_id, date=payment.payment_date)
#             if debit_account_move_id:
#                 debit_account_move = env['account.move'].browse(
#                     debit_account_move_id)
#                 check._add_operation(
#                     'debited', debit_account_move,
#                     partner=debit_account_move.partner_id,
#                     date=debit_account_move.date)

#         if supplier_reject_debit_note_id:
#             supplier_reject_debit_note = env['account.invoice'].browse(
#                 supplier_reject_debit_note_id)
#             check._add_operation(
#                 'rejected', supplier_reject_debit_note,
#                 partner=supplier_reject_debit_note.partner_id,
#                 date=supplier_reject_debit_note.date_invoice)

#         if customer_reject_debit_note_id:
#             customer_reject_debit_note = env['account.invoice'].browse(
#                 customer_reject_debit_note_id)
#             check._add_operation(
#                 'reclaimed', customer_reject_debit_note,
#                 partner=customer_reject_debit_note.partner_id,
#                 date=customer_reject_debit_note.date_invoice)
#             # TODO ver si hace falta
#             check.state = 'reclaimed'
#         elif rejection_account_move_id:
#             rejection_account_move = env['account.move'].browse(
#                 rejection_account_move_id)
#             check._add_operation(
#                 'reclaimed', rejection_account_move,
#                 partner=rejection_account_move.partner_id,
#                 date=rejection_account_move.date)

#         if replacing_check_id:
#             replacing_check = env['account.check'].browse(
#                 replacing_check_id)
#             check._add_operation(
#                 'changed', replacing_check,
#                 partner=replacing_check.partner_id,
#                 date=replacing_check.create_date)

#         if return_account_move_id:
#             return_account_move = env['account.move'].browse(
#                 return_account_move_id)
#             check._add_operation(
#                 'returned', return_account_move,
#                 partner=return_account_move.partner_id,
#                 date=return_account_move.date)
#         if original_state != check.state:
#             # if check is reclaimed it was rejected in old check module
#             if check.state == 'reclaimed' and original_state == 'rejected':
#                 continue
#             # if check is delivered it was handed in old check module
#             elif check.state == 'delivered' and original_state == 'handed':
#                 continue
#             raise ValidationError(
#                 'On check %s (id: %s) check state (%s) differs from original'
#                 ' check state (%s)' % (
#                     check.name, check.id, check.state, original_state))
