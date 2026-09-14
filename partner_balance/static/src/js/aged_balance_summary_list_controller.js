/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useState, onMounted } from "@odoo/owl";
import { download } from "@web/core/network/download";

class AgedBalanceSummaryListController extends ListController {
    static template = "partner_balance.AgedBalanceSummaryListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.companyService = useService("company");

        this.userConfig = useState({
            show_tl: false,
            show_usd: false,
        });

        onMounted(async () => {
            const cfg = await this.orm.call('partner.balance.user.config', 'get_user_config', []);
            Object.assign(this.userConfig, cfg);
        });
    }

    get isTrReport() {
        return this.props.context?.action_name === 'Aged Balance in TRY';
    }

    _exportPayload() {
        return JSON.stringify({
            domain: this.model.root.domain,
            allowed_company_ids: this.companyService.activeCompanyIds,
        });
    }

    async onExcelExport() {
        await download({
            url: "/web/aged_balance_summary_export/xlsx",
            data: { data: this._exportPayload() },
        });
    }

    async onPdfExport() {
        await download({
            url: "/web/aged_balance_summary_export/pdf",
            data: { data: this._exportPayload() },
        });
    }

    async onTrReport() {
        await this.action.doAction('partner_balance.action_aged_balance_summary_tr');
    }

    async onUsdReport() {
        await this.action.doAction('partner_balance.action_aged_balance_summary');
    }

    async openRecord(record) {
        if (this.isTrReport) {
            const partnerId = record.data.partner_id[0];
            await this.action.doAction('partner_balance.action_aged_balance_tr', {
                additionalContext: {
                    active_id: partnerId,
                    active_ids: [partnerId],
                    active_model: 'res.partner',
                    default_partner_id: partnerId,
                    report_type: 'aged',
                    action_name: 'Statement in TRY',
                },
            });
        } else {
            const action = await this.orm.call(
                "account.aged.balance.summary",
                "action_open_partner_aged_balance",
                [[record.resId]],
            );
            await this.action.doAction(action);
        }
    }
}

registry.category("views").add("aged_balance_summary", {
    ...listView,
    Controller: AgedBalanceSummaryListController,
});
