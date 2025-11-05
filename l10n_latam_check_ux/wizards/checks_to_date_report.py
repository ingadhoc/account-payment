##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import api, fields, models
from odoo.tools.sql import SQL


class AccountCheckToDateReportWizard(models.TransientModel):
    _name = "account.check.to_date.report.wizard"
    _description = "account.check.to_date.report.wizard"

    journal_id = fields.Many2one(
        "account.journal",
        string="Diario",
        domain=[
            "|",
            ("outbound_payment_method_line_ids.code", "=", "check_printing"),
            ("inbound_payment_method_line_ids.code", "=", "in_third_party_checks"),
        ],
    )
    to_date = fields.Date(
        "Hasta Fecha",
        required=True,
        default=fields.Date.today,
    )

    def action_confirm(self):
        self.ensure_one()
        # force_domain = self.journal_id and [("journal_id", "=", self.journal_id.id)] or []
        return self.env.ref("l10n_latam_check_ux.checks_to_date_report").report_action(self)

    @api.model
    def _get_checks_handed(self, journal_id, to_date):
        """
        hacemos una query que:
        * toma todos los pagos correspondientes a un cheque
        * dentro de esos pagos filtramos por los que no tengan matched_debit_ids
        * dentro de account.full.reconcile buscar todas las que tengas asocido un pago que corresponda a un cheque, una vez filtrado,
        * obtener la otra linea de ese full reconcile ya que esta corresponde a la conciliacion hecha en el date determinado
        * entonces lo que filtramos finalmente sera, los cheques aun no fueron debitados y sean de fecha anterior a la dada o los que tiene debito luego de la fecha dada

        -> en account.full.reconcile:
        self.env['account.full.reconcile'].search([]).reconciled_line_ids.move_id.payment_ids.filtered(lambda x: x.payment_method_id.code == 'own_checks').ids -> nos da los id de los pagos correspondientes a un cheque que fueron conciliados
        -> esto nos da en la fecha en la cual fueron debitados:
        self.env['account.full.reconcile'].search([]).reconciled_line_ids.filtered(lambda x: x.move_id.payment_ids.payment_method_id.code == 'own_checks').full_reconcile_id.reconciled_line_ids.filtered(lambda x: x.statement_line_id).mapped(lambda x: x.date)
        """
        query = SQL(
            """
                SELECT DISTINCT ON (t.check_id) t.check_id AS cheque FROM
                    (
                        SELECT
                            c.id as check_id,
                            ap_move.date as operation_date,
                            apm.code as operation_code
                        FROM l10n_latam_check c
                        JOIN account_payment AS ap
                            ON c.payment_id = ap.id
                        LEFT JOIN account_payment_method_line AS apml
                            ON apml.id = ap.payment_method_line_id
                        LEFT JOIN account_payment_method AS apm
                            ON apm.id = apml.payment_method_id
                        LEFT JOIN account_move AS ap_move
                            ON ap.move_id = ap_move.id
                        LEFT JOIN account_journal AS journal
                            ON ap_move.journal_id = journal.id
                        WHERE
                        c.issue_state = 'handed'
                        AND apm.code = 'own_checks'
                        AND ap_move.date <= %(to_date)s
                        ORDER BY c.id, ap_move.date desc
                    ) t
                    LEFT JOIN
                    (
                        SELECT
                            c.id as check_id,
                            MAX(aml.date) AS operation_date
                        FROM l10n_latam_check c
                        JOIN account_payment AS ap
                            ON ap.id = c.payment_id
                        JOIN account_payment_method AS apm
                            ON apm.id = ap.payment_method_id
                        JOIN account_move_line as aml
                            ON ap.move_id = aml.move_id
                        JOIN account_account aa
                            ON aa.id = aml.account_id
                        LEFT JOIN account_partial_reconcile afr_partial
                            ON  (
                                afr_partial.credit_move_id = aml.id
                                OR afr_partial.debit_move_id = aml.id
                            )
                        WHERE apm.code = 'own_checks'
                        AND aa.reconcile = true
                        GROUP BY c.id
                        HAVING BOOL_AND(afr_partial.id IS NOT NULL)
                    ) t2
                    ON t.check_id = t2.check_id
                WHERE t2.operation_date >= %(to_date)s OR t2.operation_date IS NULL
                ;
            """,
            to_date=to_date,
        )
        self.env.cr.execute(query)
        res = self.env.cr.fetchall()
        check_ids = [x[0] for x in res]
        checks = self.env["l10n_latam.check"].search([("id", "in", check_ids)])
        if journal_id:
            checks = self.env["l10n_latam.check"].search(
                [("id", "in", check_ids), ("original_journal_id", "=", journal_id)]
            )
        return checks

    @api.model
    def _get_checks_on_hand(self, journal_id, to_date):
        self.env.cr.execute("DROP TABLE IF EXISTS t;")
        # Buscamos la última operation (payment) de cada cheque
        self.env.cr.execute("""
            CREATE TEMPORARY TABLE t AS
            SELECT
                rel.check_id,
                MAX(rel.payment_id) AS payment_id
            FROM
                l10n_latam_check_account_payment_rel rel
            LEFT JOIN
                account_payment AS ap ON ap.id = rel.payment_id
            LEFT JOIN
                account_payment_method AS apm ON apm.id = ap.payment_method_id
            LEFT JOIN
                account_move AS ap_move ON ap.move_id = ap_move.id
            GROUP BY
                rel.check_id;
        """)

        self.env.cr.execute("DROP TABLE IF EXISTS t2;")
        # De la última operación de cada cheque filtramos los cheques cuya última operacioń no es manual (es decir, no
        # fue depositado) y los cheques cuya última operación es manual pero la fecha de depósito es posterior a la
        # "Hasta Fecha" del wizard de cheques a fecha.
        self.env.cr.execute(
            """
            CREATE TEMPORARY TABLE t2 AS
            SELECT
                t.check_id,
                t.payment_id
            FROM
                t
            LEFT JOIN
                account_payment AS ap ON ap.id = t.payment_id
            LEFT JOIN
                account_payment_method AS apm ON apm.id = ap.payment_method_id
            LEFT JOIN
                account_move AS ap_move ON ap.move_id = ap_move.id
            WHERE
                (apm.code != 'manual' OR (apm.code = 'manual' AND ap_move.date > %s));
            """,
            (to_date,),
        )

        # De los cheques filtrados en t2 volvemos a filtrar aquellos que tengan método de pago de cheques de terceros
        # que tengan diario actual (es decir que no hayan sido endosados) y la fecha contable de la primera operación
        # del cheque sea anterior a la "Hasta Fecha" del wizard de cheques a fecha.
        # Además sumamos aquellos cheques de terceros no endosados ni depositados cuya fecha contable de la primera
        # operación del cheque sea anterior a la "Hasta Fecha" del wizard de cheques a fecha.
        query = """
            SELECT c.id AS check_id, ap_move.date AS operation_date, apm.code AS operation_code
            FROM t2
            LEFT JOIN l10n_latam_check c ON c.id = t2.check_id
            LEFT JOIN account_payment AS ap ON ap.id = c.payment_id
            LEFT JOIN account_payment_method AS apm ON apm.id = ap.payment_method_id
            LEFT JOIN account_move AS ap_move ON ap.move_id = ap_move.id
            LEFT JOIN account_journal AS journal ON ap_move.journal_id = journal.id
            WHERE apm.code = 'new_third_party_checks'
            AND (
                c.current_journal_id IS NOT NULL
                OR EXISTS (
                    SELECT 1 FROM l10n_latam_check_account_payment_rel rel2
                    LEFT JOIN account_payment ap2 ON ap2.id = rel2.payment_id
                    LEFT JOIN account_move am2 ON am2.id = ap2.move_id
                    WHERE rel2.check_id = c.id
                    AND am2.date > %s
                    AND ap2.payment_method_id IN (
                        SELECT id FROM account_payment_method WHERE code IN ('out_third_party_checks', 'manual')
                    )
                )
            )
            AND ap_move.date <= %s
            UNION ALL
            SELECT c.id AS check_id, ap_move.date AS operation_date, apm.code AS operation_code
            FROM l10n_latam_check c
            LEFT JOIN account_payment AS ap ON ap.id = c.payment_id
            LEFT JOIN account_payment_method AS apm ON apm.id = ap.payment_method_id
            LEFT JOIN account_move AS ap_move ON ap.move_id = ap_move.id
            LEFT JOIN account_journal AS journal ON ap_move.journal_id = journal.id
            LEFT JOIN l10n_latam_check_account_payment_rel rel ON rel.check_id = c.id
            WHERE apm.code = 'new_third_party_checks' AND c.current_journal_id IS NOT NULL AND rel.check_id IS NULL AND ap_move.date <= %s;
        """
        self.env.cr.execute(query, (to_date, to_date, to_date))
        res = self.env.cr.fetchall()
        check_ids = [x[0] for x in res]
        checks = self.env["l10n_latam.check"].search([("id", "in", check_ids)])
        if journal_id:
            checks = self.env["l10n_latam.check"].search(
                [("id", "in", check_ids), ("original_journal_id", "=", journal_id)]
            )
        return checks
