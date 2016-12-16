# -*- coding: utf-8 -*-
from openupgradelib import openupgrade
from openerp.exceptions import ValidationError
from openerp.addons.account_check.models.account_check import AccountCheck


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
    old_journal_ids += change_third_journals(env)
    env['account.journal'].browse(old_journal_ids).unlink()

    # first unlink then add third issue types because if not a checkbook
    # is created for old journals and we cant unlink them
    env['account.journal']._enable_third_check_on_cash_journals()
    env['account.journal']._enable_issue_check_on_bank_journals()


def _change_journal(cr, old_journal_id, new_journal_id):
    for table in [
            'account_move', 'account_move_line', 'account_check',
            'account_payment', 'account_checkbook', 'account_voucher']:
        openupgrade.logged_query(cr, """
            UPDATE
                %s
            SET
                journal_id=%s
            WHERE journal_id = %s
            """ % (table, new_journal_id, old_journal_id),)


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
        _change_journal(cr, old_journal_id, new_journal_id)
        old_journal_ids.append(old_journal_id)
    return old_journal_ids


def change_third_journals(env):
    """
    Search for old payment_subtype = third_check journals and move to cash
    journals of each company
    """
    cr = env.cr
    old_journal_ids = []
    for company in env['res.company'].search([]):
        openupgrade.logged_query(cr, """
            SELECT
                id
            FROM account_journal
            WHERE payment_subtype = 'third_check' AND
                type in ('cash', 'bank') AND
                company_id = %s
            """, (company.id,))
        old_third_journals_read = cr.fetchall()
        if old_third_journals_read:
            new_third_journal = env['account.journal'].search([
                ('company_id', '=', company.id),
                ('type', '=', 'cash'),
            ], limit=1)
            if not new_third_journal:
                raise ValidationError(
                    'We havent found a new_third_journal for company %s' % (
                        company.id))
            for old_journal_id in old_third_journals_read[0]:
                _change_journal(cr, old_journal_id, new_third_journal.id)
                old_journal_ids.append(old_journal_id)
    return old_journal_ids


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
            move_id
        FROM
            account_voucher_copy
        WHERE
            id = %s
            """, (voucher_id,))
    read = cr.fetchall()
    if read:
        move_id = read[0]
        payment = env['account.move.line'].search([
            ('move_id', 'in', move_id), ('payment_id', '!=', False)],
            limit=1).payment_id
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
        """,)
    for read in cr.fetchall():
        (
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
            # 'currency_id': currency_id,
        }
        check = env['account.check'].create(check_vals)
        if check.type == 'third_check':
            payment = get_payment(env, voucher_id)
            if payment:
                # payment = env['account.payment'].browse(voucher_id)
                payment.write({
                    'check_ids': [(4, check.id, False)],
                    'payment_method_id': env.ref(
                        'account_check.'
                        'account_payment_method_received_third_check').id,
                })
                check._add_operation(
                    'holding', payment,
                    partner=payment.partner_id, date=payment.payment_date)

            delivery_payment = get_payment(env, third_handed_voucher_id)
            # if third_handed_voucher_id:
            #     delivery_payment = env['account.payment'].browse(
            #         third_handed_voucher_id)
            if delivery_payment:
                payment.write({
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
                    'check_ids': [(4, check.id, False)],
                    'payment_method_id': env.ref(
                        'account_check.'
                        'account_payment_method_issue_check').id,
                })
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

        if customer_reject_debit_note_id:
            customer_reject_debit_note = env['account.invoice'].browse(
                customer_reject_debit_note_id)
            check._add_operation(
                'reclaimed', customer_reject_debit_note,
                partner=customer_reject_debit_note.partner_id,
                date=customer_reject_debit_note.date_invoice)
            # TODO ver si hace falta
            check.state = 'reclaimed'
        elif rejection_account_move_id:
            rejection_account_move = env['account.move'].browse(
                rejection_account_move_id)
            check._add_operation(
                'reclaimed', rejection_account_move,
                partner=rejection_account_move.partner_id,
                date=rejection_account_move.date)

        if replacing_check_id:
            replacing_check = env['account.check'].browse(
                replacing_check_id)
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
