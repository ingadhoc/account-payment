odoo.define('pos_credit_card_installment.CreditCardInstallmentButton', function (require) {
'use strict';


    const {useState} = owl;
    const PosComponent = require('point_of_sale.PosComponent');
    const Registries = require('point_of_sale.Registries');
    const { useListener } = require("@web/core/utils/hooks");

    class CreditCardInstallmentButton extends PosComponent {
        setup() {
            super.setup();
            this.state = useState({
                card_number: '',
                lot_number: '',
                ticket_number: '',
            });
            useListener('click', this.onClick);
            useListener('send-payment', this.sendPayment);
        }
        async sendPayment() {
            console.log()
        }

    }

    CreditCardInstallmentButton.template = 'CreditCardInstallmentButton';
    Registries.Component.add(CreditCardInstallmentButton);
    return CreditCardInstallmentButton;

});
