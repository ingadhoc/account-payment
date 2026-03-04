from . import models
from . import wizards


def _update_payment_receipt_template(env):
    template = env.ref("account.mail_template_data_payment_receipt", raise_if_not_found=False)
    if template:
        template.write(
            {
                "body_html": """<div style="margin: 0px; padding: 0px;">
                                <p style="margin: 0px; padding: 0px; font-size: 13px;">
                                    Dear <t t-out="object.partner_id.name or ''">Azure Interior</t><br/><br/>
                                    Thank you for your payment.
                                    Here is your payment receipt <span style="font-weight:bold;" t-out="(object.name or '').replace('/','-') or ''">BNK1-2021-05-0002</span> amounting
                                    to <span style="font-weight:bold;" t-out="format_amount(object.payment_total, object.currency_id) or ''">$ 10.00</span> from <t t-out="object.company_id.name or ''">YourCompany</t>.
                                    <br/><br/>
                                    Do not hesitate to contact us if you have any questions.
                                    <br/><br/>
                                    Best regards,
                                    <t t-if="not is_html_empty(user.signature)">
                                        <br/><br/>
                                        <t t-out="user.signature or ''">--<br/>Mitchell Admin</t>
                                    </t>
                                </p>
                            </div>
                            """,
            }
        )
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

        if env["res.lang"].search([("code", "=", "es_419")]):
            template.with_context(lang="es_419").write({"body_html": text_es})
        if env["res.lang"].search([("code", "=", "es_AR")]):
            template.with_context(lang="es_AR").write({"body_html": text_es})


def _post_init_hooks(env):
    _update_payment_receipt_template(env)
