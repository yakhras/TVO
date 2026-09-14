/** @odoo-module **/

import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { useState, onPatched, onMounted } from "@odoo/owl";
import { PartnerBalanceToolbar } from "./components/partner_balance_toolbar";

export class PartnerBalanceListController extends ListController {
    static template = "partner_balance.PartnerBalanceListView";
    static components = {
        ...ListController.components,
        PartnerBalanceToolbar,
    };

    setup() {
        super.setup();

        // Services
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        // State
        this.state = useState({
            dateFrom: null,
            dateTo: null,
            currencyBalances: {},
            showSummary: false,
            initialBalance: 0,
        });
        this.state.showProducts = false;
        this.state.skipOpening = false;

        // User configuration for button visibility
        this.userConfig = useState({
            show_ledger: false,
            show_aged: false,
            show_excel: false,
            show_tl: false,
            show_usd: false,
            show_products: false,
            show_skip_opening: false,
        });

        onMounted(async () => {
            const cfg = await this.orm.call('partner.balance.user.config', 'get_user_config', []);
            Object.assign(this.userConfig, cfg);
        });

        onPatched(() => {
            if (this.state.showProducts && this._productData) {
                setTimeout(() => this._renderProductSubTables(), 0);
            }
        });
    }

    // -------------------------------------------------------------------------
    // Getters
    // -------------------------------------------------------------------------

    get context() {
        return this.props.context || {};
    }

    get partnerId() {
        return this.context.default_partner_id;
    }

    get isTrReport() {
        return this.context.action_name === 'Statement in TRY';
    }

    get reportType() {
        return this.context.report_type || 'ledger';
    }

    get showDateInputs() {
        return this.reportType === 'ledger';
    }

    get toolbarProps() {
        return {
            dateFrom: this.state.dateFrom,
            dateTo: this.state.dateTo,
            currencyBalances: this.state.currencyBalances,
            showSummary: this.state.showSummary,
            isTrReport: this.isTrReport,
            showProducts: this.state.showProducts,
            onToggleProducts: this.onToggleProducts.bind(this),
            skipOpening: this.state.skipOpening,
            onToggleSkipOpening: this.onToggleSkipOpening.bind(this),
            onTrReport: this.onTrReport.bind(this),
            onUsdReport: this.onUsdReport.bind(this),
            onDateChange: this.onDateChange.bind(this),
            onExcelExport: this.onExcelExport.bind(this),
            onPdfExport: this.onPdfExport.bind(this),
            reportType: this.reportType,
            showDateInputs: this.showDateInputs,
            onLedgerReport: this.onLedgerReport.bind(this),
            onAgedReport: this.onAgedReport.bind(this),
            userConfig: this.userConfig,
        };
    }


    onTrReport() {
        if (!this.partnerId) return;
        if (this.reportType === 'aged') {
            this.action.doAction('partner_balance.action_aged_balance_tr', {
                additionalContext: {
                    active_id: this.partnerId,
                    active_ids: [this.partnerId],
                    active_model: 'res.partner',
                    default_partner_id: this.partnerId,
                    partner_name: this.context.partner_name || '',
                    report_type: 'aged',
                    action_name: 'Statement in TRY',
                },
            });
        } else {
            this.action.doAction('partner_balance.action_partner_move_line_tr_value', {
                additionalContext: {
                    active_id: this.partnerId,
                    active_ids: [this.partnerId],
                    active_model: 'res.partner',
                    default_partner_id: this.partnerId,
                    partner_name: this.context.partner_name || '',
                    action_name: 'Statement in TRY',
                },
            });
        }
    }

    onUsdReport() {
        if (!this.partnerId) return;
        if (this.reportType === 'aged') {
            this.action.doAction('partner_balance.action_aged_balance', {
                additionalContext: {
                    active_id: this.partnerId,
                    active_ids: [this.partnerId],
                    active_model: 'res.partner',
                    default_partner_id: this.partnerId,
                    partner_name: this.context.partner_name || '',
                    report_type: 'aged',
                },
            });
        } else {
            this.action.doAction('partner_balance.action_partner_move_line_usd', {
                additionalContext: {
                    active_id: this.partnerId,
                    active_ids: [this.partnerId],
                    active_model: 'res.partner',
                    default_partner_id: this.partnerId,
                    partner_name: this.context.partner_name || '',
                    action_name: 'Statement of Account',
                },
            });
        }
    }

    onLedgerReport() {
        if (!this.partnerId) return;
        const actionId = this.isTrReport
            ? 'partner_balance.action_partner_move_line_tr_value'
            : 'partner_balance.action_partner_move_line_usd';
        this.action.doAction(actionId, {
            additionalContext: {
                active_id: this.partnerId,
                active_ids: [this.partnerId],
                active_model: 'res.partner',
                default_partner_id: this.partnerId,
                partner_name: this.context.partner_name || '',
                report_type: 'ledger',
            },
        });
    }

    onAgedReport() {
        if (!this.partnerId) return;
        const actionId = this.isTrReport
            ? 'partner_balance.action_aged_balance_tr'
            : 'partner_balance.action_aged_balance';
        this.action.doAction(actionId, {
            additionalContext: {
                active_id: this.partnerId,
                active_ids: [this.partnerId],
                active_model: 'res.partner',
                default_partner_id: this.partnerId,
                partner_name: this.context.partner_name || '',
                report_type: 'aged',
            },
        });
    }

    // -------------------------------------------------------------------------
    // Date Handling
    // -------------------------------------------------------------------------

    async onDateChange({ dateFrom, dateTo, originalEvent }) {
        if (!dateFrom) {
            this.state.showSummary = false;
            await this.updateViewWithDates(null, dateTo);
            return;
        }

        if (dateTo && new Date(dateTo) <= new Date(dateFrom)) {
            if (originalEvent) {
                originalEvent.target.value = '';
            }
            this.state.showSummary = false;
            this.notification.add(_t("End date must be after start date"), { type: "warning" });
            return;
        }

        await this.updateViewWithDates(dateFrom, dateTo);
        const balances = await this.getCurrencyBalance();
        this.state.currencyBalances = balances;
        const tryBalance = balances['TRY'] || {};
        this.state.initialBalance = tryBalance.opening || 0;
        this.state.showSummary = true;
    }

    async updateViewWithDates(dateFrom, dateTo) {
        let domain = [...(this.props.domain || [])];

        // Remove existing date filters only (NOT line_type)
        domain = domain.filter(filter =>
            !Array.isArray(filter) ||
            (filter[0] !== 'date' && filter[0] !== 'date_from' && filter[0] !== 'date_to')
        );

        // Add new date filters
        if (dateFrom) {
            domain.push(['date', '>=', dateFrom]);
        }
        if (dateTo) {
            domain.push(['date', '<=', dateTo]);
        }

        this.state.dateFrom = dateFrom;
        this.state.dateTo = dateTo;

        await this.model.load({
            domain,
            context: {
                ...this.context,
                date_from: dateFrom || null,
                date_to: dateTo || null,
                skip_opening: this.state.skipOpening,
            },
        });

        if (this.state.showProducts) {
            await this._fetchProductData();
            this._renderProductSubTables();
        }
    }

    async onToggleProducts() {
        this.state.showProducts = !this.state.showProducts;
        if (this.state.showProducts) {
            await this._fetchProductData();
            this._renderProductSubTables();
        } else {
            this._productData = null;
            this._removeProductSubTables();
        }
    }

    async onToggleSkipOpening() {
        this.state.skipOpening = !this.state.skipOpening;
        // Reload data with new context to recalculate cumulated_balance
        await this.updateViewWithDates(this.state.dateFrom, this.state.dateTo);
    }

    async _fetchProductData() {
        const records = this.model.root.records;
        const invoiceTypes = ['out_invoice', 'in_invoice', 'out_refund', 'in_refund'];
        const moveIds = [...new Set(
            records
                .filter(r => {
                    return invoiceTypes.includes(r.data.type_key);
                })
                .map(r => r.data.move_id && r.data.move_id[0])
                .filter(Boolean)
        )];


        if (!moveIds.length) {
            this._productData = {};
            return;
        }

        const lines = await this.orm.searchRead(
            'account.move.line',
            [['move_id', 'in', moveIds], ['display_type', '=', 'product']],
            ['move_id', 'product_id', 'quantity', 'product_uom_id', 'price_unit', 'discount', 'price_total', 'price_subtotal']
        );


        this._productData = {};
        for (const line of lines) {
            const moveId = line.move_id[0];
            if (!this._productData[moveId]) this._productData[moveId] = [];
            this._productData[moveId].push(line);
        }
    }

    _renderProductSubTables() {
        this._removeProductSubTables();
        if (!this._productData) return;

        const tableBody = document.querySelector('.o_list_view .o_list_table tbody');
        if (!tableBody) return;

        const rows = tableBody.querySelectorAll(':scope > .o_data_row');
        for (const row of rows) {
            const datapointId = row.dataset.id;
            const record = this.model.root.records.find(r => r.id === datapointId);
            if (!record) continue;

            const moveId = record.data.move_id && record.data.move_id[0];
            if (!moveId || !this._productData[moveId]) continue;

            const lines = this._productData[moveId];
            const colSpan = row.cells.length;

            const subRow = this._createProductSubRow(lines, colSpan);
            row.after(subRow);
        }
    }

    /**
     * Build a product sub-row using safe DOM APIs (no innerHTML).
     * @param {Array} lines - product line data objects
     * @param {number} colSpan - number of columns to span
     * @returns {HTMLTableRowElement}
     */
    _createProductSubRow(lines, colSpan) {
        const tr = document.createElement('tr');
        tr.classList.add('o_product_subtable_row');

        const td = document.createElement('td');
        td.setAttribute('colspan', colSpan);
        Object.assign(td.style, {
            padding: '4px 8px 4px 40px',
            backgroundColor: '#f0f9ff',
            borderTop: 'none',
        });

        const table = document.createElement('table');
        table.className = 'table table-sm table-bordered mb-0';
        table.style.fontSize = '0.85em';

        // Header
        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        headRow.style.backgroundColor = '#e0f2fe';
        const headers = [
            { text: 'Product', cls: '' },
            { text: 'Qty', cls: 'text-end' },
            { text: 'UoM', cls: '' },
            { text: 'Unit Price', cls: 'text-end' },
            { text: 'Disc. %', cls: 'text-end' },
            { text: 'Tax', cls: 'text-end' },
            { text: 'Total', cls: 'text-end' },
        ];
        for (const h of headers) {
            const th = document.createElement('th');
            th.textContent = h.text;
            if (h.cls) th.className = h.cls;
            headRow.appendChild(th);
        }
        thead.appendChild(headRow);
        table.appendChild(thead);

        // Body
        const tbody = document.createElement('tbody');
        for (const l of lines) {
            const dataRow = document.createElement('tr');
            const cells = [
                { text: l.product_id ? l.product_id[1] : '', cls: '' },
                { text: String(l.quantity), cls: 'text-end' },
                { text: l.product_uom_id ? l.product_uom_id[1] : '', cls: '' },
                { text: Number(l.price_unit).toFixed(2), cls: 'text-end' },
                { text: String(l.discount || 0), cls: 'text-end' },
                { text: Number(l.price_total - l.price_subtotal).toFixed(2), cls: 'text-end' },
                { text: Number(l.price_total).toFixed(2), cls: 'text-end' },
            ];
            for (const c of cells) {
                const cell = document.createElement('td');
                cell.textContent = c.text;
                if (c.cls) cell.className = c.cls;
                dataRow.appendChild(cell);
            }
            tbody.appendChild(dataRow);
        }
        table.appendChild(tbody);
        td.appendChild(table);
        tr.appendChild(td);
        return tr;
    }

    _removeProductSubTables() {
        document.querySelectorAll('.o_product_subtable_row').forEach(el => el.remove());
    }

    // -------------------------------------------------------------------------
    // Summary Display
    // -------------------------------------------------------------------------

    async getCurrencyBalance() {
        if (!this.partnerId || !this.state.dateFrom) return {};

        const result = await this.orm.call(
            'account.move.line.report',
            'get_opening_balance_value',
            [this.partnerId, this.state.dateFrom, this.isTrReport]
        );
        return result;
    }


    // -------------------------------------------------------------------------
    // Export
    // -------------------------------------------------------------------------

    async _buildExportPayload() {
        const columns = this.props.archInfo.columns
            .filter(col => col.type === 'field')
            .filter(col => !col.optional || this.optionalActiveFields[col.name])
            .filter(col => !evaluateBooleanExpr(col.column_invisible, this.props.context))
            .filter(col => this.props.fields[col.name]?.exportable !== false);

        const exportedFields = columns.map(col => ({
            name: col.name,
            label: this.props.fields[col.name].string,
            store: this.props.fields[col.name].store,
            type: this.props.fields[col.name].type,
        }));

        let ids = false;
        if (!this.model.root.isDomainSelected) {
            const resIds = await this.model.root.getResIds(true);
            ids = resIds.length > 0 && resIds;
        }

        return JSON.stringify({
            model: this.model.root.resModel,
            fields: exportedFields,
            ids: ids,
            domain: this.model.root.domain,
            groupby: this.model.root.groupBy,
            context: {
                ...this.context,
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
                show_products: this.state.showProducts,
                skip_opening: this.state.skipOpening,
            },
            import_compat: false,
        });
    }

    _exportUrl(extension) {
        const basePath = this.reportType === 'aged' ? '/web/aged_balance_export' : '/web/balance_export';
        return `${basePath}/${extension}`;
    }

    async onExcelExport() {
        await download({
            data: { data: await this._buildExportPayload() },
            url: this._exportUrl('xlsx'),
        });
    }

    async onPdfExport() {
        await download({
            data: { data: await this._buildExportPayload() },
            url: this._exportUrl('pdf'),
        });
    }
}
