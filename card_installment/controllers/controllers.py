# -*- coding: utf-8 -*-
# from odoo import http


# class CardInstallment(http.Controller):
#     @http.route('/card_installment/card_installment', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/card_installment/card_installment/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('card_installment.listing', {
#             'root': '/card_installment/card_installment',
#             'objects': http.request.env['card_installment.card_installment'].search([]),
#         })

#     @http.route('/card_installment/card_installment/objects/<model("card_installment.card_installment"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('card_installment.object', {
#             'object': obj
#         })
