odoo.define('pos_credit_card_installment.CreditCardInstallmentPopup', function (require) {
'use strict';

    const Registries = require('point_of_sale.Registries');
    const AbstractAwaitablePopup = require('point_of_sale.AbstractAwaitablePopup');
    const {useState} = owl;


    class CreditCardInstallmentPopup extends AbstractAwaitablePopup {
		setup() {
		    super.setup();
		    this.state = useState({card_number: this.props.card_number, lot_number: this.props.lot_number, ticket_number: this.props.ticket_number,  product_id: this.props.product_id})
            this.changes = {};
		}
		getPayLoad(){
		    return this.changes;
        }

        async confirm() {
            console.log('test confirm')
            // var allowConfirmChanges = true;
            // _.each(Object.values(this.changes), (updates) =>
            //     _.each(Object.values(updates), (value) => {
            //         if (isNaN(value)) {
            //             allowConfirmChanges = false;
            //         }
            //     })
            // );
            // if (allowConfirmChanges) {
            //     this.env.posbus.trigger("close-popup", {
            //         popupId: this.props.id,
            //         response: {confirmed: true, payload: await this.getPayload()},
            //     });
            // }
        }

        CreditCardInstallmentPopup(item) {
            this.env.posbus.trigger('close-popup', {
                popupId: this.props.id,
                response: {confirmed: true, payload: null},
            });
        }
    }

    CreditCardInstallmentPopup.template = 'CreditCardInstallmentPopup';
    CreditCardInstallmentPopup.defaultProps = {
        confirmText: 'Confirm',
        cancelText: 'Cancel',
    };
    Registries.Component.add(CreditCardInstallmentPopup);
    return CreditCardInstallmentPopup

});
