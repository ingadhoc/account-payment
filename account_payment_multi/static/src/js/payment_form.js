odoo.define("account_payment_multi.payment_form", (require) => {
  const checkoutForm = require("payment.checkout_form");
  const manageForm = require("payment.manage_form");

  const PaymentMixin = {
    // --------------------------------------------------------------------------
    // Private
    // --------------------------------------------------------------------------

    /**
     * Add `invoice_id` to the transaction route params if it is provided.
     *
     * @override method from payment.payment_form_mixin
     * @private
     * @param {String} code - The provider code of the selected payment option.
     * @param {Number} paymentOptionId - The id of the selected payment option.
     * @param {String} flow - The online payment flow of the selected payment option.
     * @returns {Object} The extended transaction route params.
     */
    _prepareTransactionRouteParams: function (code, paymentOptionId, flow) {
      const transactionRouteParams = this._super(...arguments);
      return {
        ...transactionRouteParams,
        invoice_ids: this.txContext.invoiceIds ? this.txContext.invoiceIds : null,
      };
    },
  };

  checkoutForm.include(PaymentMixin);
  manageForm.include(PaymentMixin);
});
