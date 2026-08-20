/** @odoo-module **/
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";

export class LogisticsDashboard extends Component {
    static template = "logistics.LogisticsDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ kpis: {}, upcomingArrivals: [], loaded: false });

        onWillStart(async () => {
            const data = await this.orm.call("logistics.dashboard", "get_dashboard_data", []);
            this.state.kpis = data.kpis;
            this.state.upcomingArrivals = data.upcoming_arrivals;
            this.state.loaded = true;
        });
    }

    openDeals(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Purchase Agreements",
            res_model: "purchase.requisition",
            views: [[false, "list"], [false, "form"]],
            domain: state ? [["state", "=", state]] : [],
        });
    }

    openContainers(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Containers",
            res_model: "logistics.container",
            views: [[false, "list"], [false, "form"]],
            domain: state ? [["state", "=", state]] : [],
        });
    }

    openBillLadings(docsDraft, docsOriginal) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Bills of Lading",
            res_model: "logistics.bill.lading",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["number", "!=", false],
                ["number", "!=", ""],
                ["docs_draft", "=", docsDraft],
                ["docs_original", "=", docsOriginal],
            ],
        });
    }

    fmtCurrency(amount, currencyTuple) {
        if (!currencyTuple) {
            return amount;
        }
        return formatCurrency(amount, currencyTuple[0]);
    }

    openContainerLine(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "logistics.container.line",
            res_id: id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("logistics_dashboard", LogisticsDashboard);
