odoo.define('pos_credit_card_installment.PaymentScreenPaymentLines', function (require) {
    'use strict';

    const PaymentScreenPaymentLines = require('point_of_sale.PaymentScreenPaymentLines');
    const Registries = require('point_of_sale.Registries');

    const InstallmentPaymentLines = (PaymentScreenPaymentLines) =>
        class extends PaymentScreenPaymentLines {
            /**
             * @override
             */
            /**
			 * Save to field `changes` all input changes from the form fields.
			 */
			captureChange(event) {
			    console.log('Eventooooooooo')
			    console.log(event.target)
				this.env.pos.installment = event.target.value;
				this.env.pos.surchage_coefficient = event.target.value;
				this.env.pos.surchage_coefficient = event.target.value;
			}

        };

    Registries.Component.extend(PaymentScreenPaymentLines, InstallmentPaymentLines);
    return PaymentScreenPaymentLines;
});
