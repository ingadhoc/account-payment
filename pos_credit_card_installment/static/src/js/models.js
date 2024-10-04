odoo.define('pos_credit_card_installment.models', function (require) {
    "use strict";

    const {PosGlobalState} = require('point_of_sale.models');
    const Registries = require('point_of_sale.Registries');

    const PosCreditCarInstallment = (PosGlobalState) => class CreditCarInstallmentGlobalState extends PosGlobalState {
        constructor(obj) {
            super(obj);
            this.installment = null;
            this.surchage_coefficient = null;
        }

        //@override
        async _processData(loadedData) {
            await super._processData(...arguments);
            this.account_card_installment = loadedData['account.card.installment'];
        }

        _save_to_server (orders, options) {
            if (!orders || !orders.length) {
                return Promise.resolve([]);
            }
            this.set_synch('connecting', orders.length);
            options = options || {};

            var self = this;
            var timeout = typeof options.timeout === 'number' ? options.timeout : 30000 * orders.length;

            // Keep the order ids that are about to be sent to the
            // backend. In between create_from_ui and the success callback
            // new orders may have been added to it.
            var order_ids_to_sync = _.pluck(orders, 'id');

            // we try to send the order. shadow prevents a spinner if it takes too long. (unless we are sending an invoice,
            // then we want to notify the user that we are waiting on something )
            var args = [_.map(orders, function (order) {
                    order.to_invoice = options.to_invoice || false;
                    return order;
                })];
            args.push(options.draft || false);
            const installment = this.env.pos.installment;
            args[0][0]['data']['installment'] = installment
            console.log('Argumentosssssss newwwwwwwwwwwww')
            console.log(args)
            return this.env.services.rpc({
                    model: 'pos.order',
                    method: 'create_from_ui',
                    args: args,
                    kwargs: {context: this.env.session.user_context},
                }, {
                    timeout: timeout,
                    shadow: !options.to_invoice
                })
                .then(function (server_ids) {
                    _.each(order_ids_to_sync, function (order_id) {
                        self.db.remove_order(order_id);
                    });
                    self.failed = false;
                    self.set_synch('connected');
                    return server_ids;
                }).catch(function (error){
                    console.warn('Failed to send orders:', orders);
                    if(error.code === 200 ){    // Business Logic Error, not a connection problem
                        // Hide error if already shown before ...
                        if ((!self.failed || options.show_error) && !options.to_invoice) {
                            self.failed = error;
                            self.set_synch('error');
                            throw error;
                        }
                    }
                    self.set_synch('disconnected');
                    throw error;
                });
        }

    }
    Registries.Model.extend(PosGlobalState, PosCreditCarInstallment);

});
