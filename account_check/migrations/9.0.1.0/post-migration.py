# -*- coding: utf-8 -*-
from openupgradelib import openupgrade
from openerp.exceptions import ValidationError


@openupgrade.migrate(use_env=True)
def migrate(env, version):
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


    # openupgrade.logged_query(cr, """
    #     SELECT
    #         id
    #     FROM account_journal
    #     WHERE payment_subtype in ('issue_check', 'third_check') AND
    #         type in ('cash', 'bank')
    #     """,)
    # journals_read = cr.fetchall()
    # print ' journals_read', journals_read
    # if journals_read:
    #     journals = env['account.journal'].search([('id', 'in', journals_read)])
    #     journals.unlink()
    # env['account.journal'].search()


def add_operations(env):
    cr = env.cr
    for check in env['account.check'].search([]):
        openupgrade.logged_query(cr, """
            SELECT
                state,
                voucher_id,
                company_currency_amount,
                supplier_reject_debit_note_id,
                rejection_account_move_id,
                replacing_check_id,
                debit_account_move_id,
                third_handed_voucher_id,
                customer_reject_debit_note_id,
                deposit_account_move_id,
                return_account_move_id
            FROM account_check
            WHERE id = %s
            """, (check.id,))
        read = cr.fetchall()
        if not read:
            raise ValidationError('We could not found check %s' % check.id)
        (
            original_state,
            voucher_id,
            company_currency_amount,
            supplier_reject_debit_note_id,
            rejection_account_move_id,
            replacing_check_id,
            debit_account_move_id,
            third_handed_voucher_id,
            customer_reject_debit_note_id,
            deposit_account_move_id,
            return_account_move_id) = read[0]

        if company_currency_amount:
            check.amount_currency = check.amount
            check.amount = company_currency_amount
            # check.currency_id = company_currency_amount

        if check.type == 'third_check':
            if voucher_id:
                payment = env['account.payment'].browse(voucher_id)
                check._add_operation(
                    'holding', payment,
                    partner=payment.partner_id, date=payment.payment_date)

            if third_handed_voucher_id:
                delivery_payment = env['account.payment'].browse(
                    third_handed_voucher_id)
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
            if voucher_id:
                payment = env['account.payment'].browse(voucher_id)
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

# def update_receiptbook_type(env):
#     cr = env.cr
#     openupgrade.map_values(
#         cr,
#         'type', 'partner_type',
#         # openupgrade.get_legacy_name('type'), 'partner_type',
#         [('receipt', 'customer'), ('payment', 'supplier')],
#         table='account_payment_receiptbook', write='sql')


# def install_original_modules(env):
#     cr = env.cr
#     openupgrade.logged_query(cr, """
#         UPDATE ir_module_module
#         SET state = 'to install'
#         WHERE name in ('l10n_ar_account')
#         """)


# def set_company_loc_ar(env):
#     cr = env.cr
#     openupgrade.map_values(
#         cr,
#         # openupgrade.get_legacy_name('type_tax_use'), 'localization',
#         'use_argentinian_localization', 'localization',
#         # [('all', 'none')],
#         [(True, 'argentina')],
#         table='res_company', write='sql')
