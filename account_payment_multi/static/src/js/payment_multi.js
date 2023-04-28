odoo.define('account_payment.multi', function (require) {
    'use strict';
    
    const core = require('web.core');
    const publicWidget = require('web.public.widget');
    const Dialog = require('web.Dialog');
    const _t = core._t;

    publicWidget.registry.AccountPaymentWidget = publicWidget.Widget.extend({
        selector: '.payment_multi_table',
        events: {
            'change .checkbox_amount_residual': '_onChangeCheckboxAmountResidual',
            'click .oe_multi_pay_now': '_onPayNowBtnClick',
        },
        init: function () {
            this._super.apply(this, arguments);
            //this._computeAmount();
        },
        _onChangeCheckboxAmountResidual: function(event) {
            this._computeAmount()            
        },
        _computeAmount: function(){
            var items = this.el.getElementsByClassName('checkbox_amount_residual');
            let total = 0;
            let currency = false; 
            let old_group = false; 
            let group = false; 
            console.log(group);
            for (let i = 0; i < items.length; i++) {
                if (items[i].checked){
                    old_group = group; 
                    group = items[i].dataset.invoiceGroup;
                    currency = items[i].dataset.currencyName;
                    if (old_group && group != old_group){
                        items[i].checked = false;
                        return new Dialog(null, {
                            title: _t("Error in selection"),
                            size: 'medium',
                            $content: _t(`<p>selected invoices must be in the same currency, partner and company</p>`),
                            buttons: [{text: _t("Ok"), close: true}]
                        }).open();
            
                    }
                    total = total + parseFloat(items[i].dataset.amountResidual);
                }
            }
            this.el.querySelectorAll('.oe_amount').forEach((selector) =>selector.innerHTML=currency + ' ' + total.toFixed(2));
            if (total){
                this.el.querySelectorAll('.multi_payment_selector').forEach((selector) =>selector.classList.remove('invisible'));
            } else {
                this.el.querySelectorAll('.multi_payment_selector').forEach((selector) =>selector.classList.add('invisible'));
            }
        }, 
        _onPayNowBtnClick: function(event){
            var items = this.el.getElementsByClassName('checkbox_amount_residual');
            let total = 0;
            let invoices = [];
            for (let i = 0; i < items.length; i++) {
                if (items[i].checked){
                    total = total + parseFloat(items[i].dataset.amountResidual);
                    invoices.push({id : parseInt(items[i].dataset.invoiceId), token: items[i].dataset.accessToken})
                }
            }
            let params = {invoice_ids: invoices, amount: total} 
            return this._rpc({
                route: "/payment/invoice_multi_link",
                params: params,
            }).then(async data => {
                window.location = data;
            });
            
        }
    });
});
