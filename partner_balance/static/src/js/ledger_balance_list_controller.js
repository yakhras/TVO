/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState, onMounted } from "@odoo/owl";
import { download } from "@web/core/network/download";

class LedgerBalanceListController extends ListController {
    static template = "partner_balance.LedgerBalanceListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");

        this.userConfig = useState({
            show_tl: false,
            show_usd: false,
        });

        onMounted(async () => {
            const cfg = await this.orm.call('partner.balance.user.config', 'get_user_config', []);
            Object.assign(this.userConfig, cfg);
        });
    }

    async onExcelExport() {
        await download({
            url: "/web/ledger_balance_export/xlsx",
            data: {},
        });
    }

    async onPdfExport() {
        await download({
            url: "/web/ledger_balance_export/pdf",
            data: {},
        });
    }

    get isSaleView() {
        return !!this.props.context?.is_sale_view;
    }

    get isTrReport() {
        return this.props.context?.action_name === 'Ledger Balance in TRY';
    }

    async onSaleView() {
        await this.action.doAction('partner_balance.action_sale_partner_balance_report');
    }

    async onTrReport() {
        if (this.isSaleView) {
            await this.action.doAction('partner_balance.action_sale_ledger_balance_tr');
        } else {
            await this.action.doAction('partner_balance.action_ledger_balance_tr');
        }
    }

    async onUsdReport() {
        if (this.isSaleView) {
            await this.action.doAction('partner_balance.action_sale_partner_balance_report');
        } else {
            await this.action.doAction('partner_balance.action_partner_balance_menu_report');
        }
    }

    async openRecord(record) {
        const action = await this.orm.call(
            "account.ledger.balance",
            "action_open_partner_statement",
            [[record.resId]],
        );
        await this.action.doAction(action);
    }
}

registry.category("views").add("ledger_balance", {
    ...listView,
    Controller: LedgerBalanceListController,
});
