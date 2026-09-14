/** @odoo-module **/

import { Component, useRef } from "@odoo/owl";

export class PartnerBalanceToolbar extends Component {
    static template = "partner_balance.PartnerBalanceToolbar";

    static props = {
        dateFrom: { type: [String, { value: null }], optional: true },
        dateTo: { type: [String, { value: null }], optional: true },
        currencyBalances: { type: Object, optional: true },
        showSummary: { type: Boolean, optional: true },
        isTrReport: { type: Boolean, optional: true },
        onTrReport: { type: Function },
        onDateChange: { type: Function },
        onExcelExport: { type: Function },
        onPdfExport: { type: Function },
        showProducts: { type: Boolean, optional: true }, onToggleProducts: { type: Function },
        skipOpening: { type: Boolean, optional: true },
        onToggleSkipOpening: { type: Function },
        onUsdReport: { type: Function },
        reportType: { type: String, optional: true },
        showDateInputs: { type: Boolean, optional: true },
        onLedgerReport: { type: Function },
        onAgedReport: { type: Function },
        userConfig: { type: Object, optional: true },
    };

    setup() {
        this.dateFromRef = useRef("dateFrom");
        this.dateToRef = useRef("dateTo");
    }

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    handleDateChange(ev) {
        this.props.onDateChange({
            dateFrom: this.dateFromRef.el?.value || null,
            dateTo: this.dateToRef.el?.value || null,
            originalEvent: ev,
        });
    }

    handleExcelExport() {
        this.props.onExcelExport();
    }

    handlePdfExport() {
        this.props.onPdfExport();
    }

    handleTrReport() {
        this.props.onTrReport();
    }

    handleUsdReport() {
        this.props.onUsdReport();
    }

    handleToggleProducts() { 
        this.props.onToggleProducts(); 
    }

    handleToggleSkipOpening() {
        this.props.onToggleSkipOpening();
    }

    handleLedgerReport() {
        this.props.onLedgerReport();
    }

    handleAgedReport() {
        this.props.onAgedReport();
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    formatCurrency(value) {
        return Number(value || 0).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    get currencyEntries() {
        return Object.entries(this.props.currencyBalances || {});
    }
}
