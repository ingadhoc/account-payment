/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";
import PaymentForm from '@payment/js/payment_form';


publicWidget.registry.portalDetails = publicWidget.Widget.extend({
    selector: '.payment_multi_table',
    events: {
        'change .checkbox_amount_residual': '_selectCheckboxInvoice',
        'click .oe_multi_pay_now': '_onPaySelectedBtnClick',
    },

    _selectCheckboxInvoice: function(events) {
        var currentInvoice = events.currentTarget
        var startDueDate = currentInvoice.dataset.dueDate; 
        var startId = currentInvoice.dataset.invoiceId;

        var invoices = Array.from(this.el.getElementsByClassName('checkbox_amount_residual'));
        
        // Deselect all the invoices when deselecting one of them
        invoices.forEach(invoice => {
            if (invoice !== currentInvoice) {
                invoice.checked = false;
            }
        });

        // Select the ones below
        invoices.forEach(invoice => {
            var dueDate = invoice.dataset.dueDate;
            var invoiceId = parseInt(invoice.dataset.invoiceId, 10);

            if (dueDate < startDueDate || (dueDate === startDueDate && invoiceId < startId)) {
                invoice.checked = true;
            }
        });

    },

    _onPaySelectedBtnClick: function(events){
        
        // Find the first one to be paid
        let maxInvoice = null;
        var invoices = Array.from(this.el.getElementsByClassName('checkbox_amount_residual')).filter(invoice => invoice.checked);

        invoices.forEach(invoice => {
            const dueDate = invoice.dataset.dueDate;
            const invoiceId = parseInt(invoice.dataset.invoiceId, 10);

            if (
                !maxInvoice ||
                dueDate > maxInvoice.dataset.dueDate ||
                (dueDate === maxInvoice.dataset.dueDate &&
                invoiceId > parseInt(maxInvoice.dataset.invoiceId, 10))
            ) {
                maxInvoice = invoice;
            }
        });


        if (maxInvoice) {
            var maxInvoiceId =  parseInt(maxInvoice.dataset.invoiceId, 10)
            const url = `/my/invoices/selected?invoice_id=${maxInvoiceId}`;
            window.location.href = url;
        } else {
            console.warn("No invoice selected.");
        }
    },

})

PaymentForm.include({
    /**
     * Add reference parameter for multiple payment
     *
     * @override method from @payment/js/payment_form
     * @private
     * @return {object} 
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);

        transactionRouteParams.payment_reference = this.paymentContext.paymentReference;

        return transactionRouteParams;
    },
});
