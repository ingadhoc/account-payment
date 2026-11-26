from odoo import models


class BaseLanguageInstall(models.TransientModel):
    _inherit = "base.language.install"

    def lang_install(self):
        res = super().lang_install()

        es_langs = self.lang_ids.filtered(lambda x: x.code in ["es_419", "es_AR"])
        if es_langs:
            template = self.env.ref("account.mail_template_data_payment_receipt", raise_if_not_found=False)
            if template:
                text_es = """<div style="margin: 0px; padding: 0px;">
                                <p style="margin: 0px; padding: 0px; font-size: 13px;">
                                    Apreciable <t t-out="object.partner_id.name or ''">Azure Interior</t><br/><br/>
                                    Gracias por su pago.
                                    Aquí está el recibo de su pago <span style="font-weight:bold;" t-out="(object.name or '').replace('/','-') or ''">BNK1-2021-05-0002</span> por un total
                                    de <span style="font-weight:bold;" t-out="format_amount(object.payment_total, object.currency_id) or ''">$ 10.00</span> de <t t-out="object.company_id.name or ''">SuEmpresa</t>.
                                    <br/><br/>
                                    No dude en contactarnos si tiene alguna pregunta.
                                    <br/><br/>
                                    Saludos,
                                    <t t-if="not is_html_empty(user.signature)">
                                        <br/><br/>
                                        <t t-out="user.signature or ''">--<br/>Mitchell Admin</t>
                                    </t>
                                </p>
                            </div>
                            """
                for lang in es_langs:
                    template.with_context(lang=lang.code).write({"body_html": text_es})

        return res
