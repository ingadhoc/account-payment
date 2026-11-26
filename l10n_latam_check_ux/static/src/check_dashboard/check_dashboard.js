import { registry } from "@web/core/registry";
import { ORM } from "@web/core/orm_plugin";
import { formatMonetary } from "@web/views/fields/formatters";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";

import { Component, onWillStart, proxy, t, usePlugin, useProps } from "@odoo/owl";

/**
 * KPI cards shown on top of a checks list: one per check state, with count and amount, plus the checks due
 * this week. A click applies the filters of the card on the list, replacing the current search.
 */
export class CheckDashboard extends Component {
    static template = "l10n_latam_check_ux.CheckDashboard";

    props = useProps({ section: t.string() });
    orm = usePlugin(ORM);

    setup() {
        this.state = proxy({ cards: [] });
        onWillStart(async () => {
            this.state.cards = await this.orm.call("l10n_latam.check", "get_check_dashboard_data", [
                this.props.section,
            ]);
        });
    }

    formatAmount(amount) {
        return formatMonetary(amount.amount, { currencyId: amount.currency_id });
    }

    applyCard(card) {
        const searchModel = this.env.searchModel;
        const items = searchModel.getSearchItems((item) => card.filters.includes(item.name));
        searchModel.query.length = 0;
        for (const item of items) {
            searchModel.toggleSearchItem(item.id);
        }
    }
}

export class ThirdPartyCheckListRenderer extends ListRenderer {
    static template = "l10n_latam_check_ux.CheckListRenderer";
    static components = { ...ListRenderer.components, CheckDashboard };

    get checkDashboardSection() {
        return "third_party";
    }
}

export class OwnCheckListRenderer extends ThirdPartyCheckListRenderer {
    get checkDashboardSection() {
        return "own";
    }
}

registry.category("views").add("l10n_latam_third_party_check_list", {
    ...listView,
    Renderer: ThirdPartyCheckListRenderer,
});
registry.category("views").add("l10n_latam_own_check_list", {
    ...listView,
    Renderer: OwnCheckListRenderer,
});
