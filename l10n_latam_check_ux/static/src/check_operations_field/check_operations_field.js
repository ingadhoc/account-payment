import { _t } from "@web/core/l10n/translation";
import { ORM } from "@web/core/orm_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, usePlugin, useProps } from "@odoo/owl";

/**
 * The payments of a check, one per line, with a button to the list of its operations. Both live in one
 * column, so hiding the optional column hides the button too.
 */
export class CheckOperationsField extends Component {
    static template = "l10n_latam_check_ux.CheckOperationsField";

    props = useProps(standardFieldProps);
    orm = usePlugin(ORM);

    setup() {
        this.action = useService("action");
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    async openOperations() {
        const action = await this.orm.call("l10n_latam.check", "button_open_check_operations", [
            [this.props.record.resId],
        ]);
        await this.action.doAction(action);
    }
}

registry.category("fields").add("l10n_latam_check_operations", {
    component: CheckOperationsField,
    displayName: _t("Check Operations"),
    supportedTypes: ["text"],
});
