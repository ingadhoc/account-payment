import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

import { Component, onWillStart, useProps } from "@odoo/owl";

/**
 * Checks dashboard: one card per check state, with count and amount, for third party and own checks.
 * Each card opens the checks list filtered by its state.
 */
export class CheckDashboard extends Component {
    static template = "l10n_latam_check_ux.CheckDashboard";
    static components = { ControlPanel };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        onWillStart(async () => {
            this.sections = await this.orm.call("l10n_latam.check", "get_check_dashboard_data", []);
        });
    }

    formatAmount(amount) {
        return formatMonetary(amount.amount, { currencyId: amount.currency_id });
    }

    async openCard(section, card) {
        const action = await this.orm.call("l10n_latam.check", "action_open_dashboard_card", [
            section.key,
            card.key,
        ]);
        return this.actionService.doAction(action);
    }
}

registry.category("actions").add("l10n_latam_check_dashboard", CheckDashboard);
