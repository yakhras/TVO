/** @odoo-module **/
import { Component, useState, useRef, useEffect, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { loadBundle } from "@web/core/assets";

// Purchase Agreement statuses shown in the pie chart, with their Bootstrap color names
const DEAL_SEGMENTS = [
    { state: "draft", label: "Draft", kpi: "deals_draft", color: "secondary", fallback: "#6c757d" },
    { state: "confirmed", label: "Confirmed", kpi: "deals_confirmed", color: "info", fallback: "#0dcaf0" },
    { state: "done", label: "Closed", kpi: "deals_closed", color: "success", fallback: "#198754" },
    { state: "cancel", label: "Cancelled", kpi: "deals_cancelled", color: "danger", fallback: "#dc3545" },
];

// Bill of Lading document stages, top to bottom in the stacked bar, with the
// docs_draft / docs_original flags each stage filters on
const BL_SEGMENTS = [
    { key: "pending", label: "Docs Pending", kpi: "bl_docs_pending", color: "secondary", draft: false, original: false },
    { key: "draft", label: "Draft Received", kpi: "bl_docs_draft", color: "warning", draft: true, original: false },
    { key: "original", label: "Original Received", kpi: "bl_docs_original", color: "success", draft: true, original: true },
];

// Every non-empty slice (or bar block) is drawn with at least this share of the pie, so its
// "label + count" fits inside it. Labels and tooltips keep the real counts.
const MIN_SLICE_SHARE = 0.15;
// Labels sit at this fraction of the radius (wider than the slice centroid)
const LABEL_RADIUS = 0.62;

/**
 * Display shares for the pie and the BL stacked bar: small non-zero counts are
 * raised to MIN_SLICE_SHARE and the rest is split among the other counts in
 * proportion to their real values; zero counts get nothing. Shares sum to 1.
 * Expects at least one non-zero count (the callers handle the empty case).
 */
function displayShares(counts) {
    const nonZero = counts.filter((c) => c > 0).length;
    if (nonZero * MIN_SLICE_SHARE >= 1) {
        return counts.map((c) => (c > 0 ? 1 / nonZero : 0));
    }
    // Raising a slice shrinks the others, which can push another under the
    // minimum, so repeat until no more slices need raising
    const raised = new Set();
    for (;;) {
        const free = 1 - raised.size * MIN_SLICE_SHARE;
        const freeTotal = counts.reduce((sum, c, i) => (raised.has(i) ? sum : sum + c), 0);
        const shares = counts.map((c, i) =>
            raised.has(i) ? MIN_SLICE_SHARE : (c / freeTotal) * free
        );
        const newlyRaised = shares
            .map((s, i) => (counts[i] > 0 && !raised.has(i) && s < MIN_SLICE_SHARE ? i : -1))
            .filter((i) => i >= 0);
        if (!newlyRaised.length) {
            return shares;
        }
        newlyRaised.forEach((i) => raised.add(i));
    }
}

/**
 * Chart.js plugin drawing each non-empty slice's label and real count inside it.
 */
function sliceLabelsPlugin(segments, colors) {
    return {
        id: "logisticsSliceLabels",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            ctx.save();
            ctx.textBaseline = "middle";
            ctx.textAlign = "center";
            chart.getDatasetMeta(0).data.forEach((arc, index) => {
                const seg = segments[index];
                if (!seg.count) {
                    return;
                }
                const mid = (arc.startAngle + arc.endAngle) / 2;
                const radius = arc.outerRadius * LABEL_RADIUS;
                const x = arc.x + Math.cos(mid) * radius;
                const y = arc.y + Math.sin(mid) * radius;
                ctx.fillStyle = readableTextColor(colors[index]);
                ctx.font = "12px sans-serif";
                ctx.fillText(seg.label, x, y - 8);
                ctx.font = "bold 14px sans-serif";
                ctx.fillText(String(seg.count), x, y + 8);
            });
            ctx.restore();
        },
    };
}

// Black or white text, whichever reads better on the given hex background
function readableTextColor(hex) {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    if (!m) {
        return "#fff";
    }
    const [r, g, b] = m.slice(1).map((h) => parseInt(h, 16));
    return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#212529" : "#fff";
}

export class LogisticsDashboard extends Component {
    static template = "logistics.LogisticsDashboard";
    static props = ["*"];

    // Bootstrap color name per container state (column headers and tiles)
    containerStateColors = {
        purchase: "secondary",
        oversea: "warning",
        at_port: "warning",
        arrived: "danger",
        antrepo: "success",
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            kpis: {},
            containerStates: [],
            upcomingArrivals: [],
            upcomingHasMore: false,
            loaded: false,
        });

        this.dealsChartRef = useRef("dealsChart");
        this.dealsChart = null;

        onWillStart(async () => {
            const [data] = await Promise.all([
                this.orm.call("logistics.dashboard", "get_dashboard_data", []),
                loadBundle("web.chartjs_lib"),
            ]);
            this.state.kpis = data.kpis;
            this.state.containerStates = data.container_states;
            this.state.upcomingArrivals = data.upcoming_arrivals;
            this.state.upcomingHasMore = data.upcoming_arrivals_has_more;
            this.state.loaded = true;
        });

        useEffect(
            (canvas) => {
                if (canvas) {
                    this.renderDealsChart(canvas);
                }
            },
            () => [this.dealsChartRef.el]
        );
        onWillUnmount(() => this.dealsChart?.destroy());
    }

    get dealSegments() {
        return DEAL_SEGMENTS.map((seg) => ({ ...seg, count: this.state.kpis[seg.kpi] || 0 }));
    }

    get dealsTotal() {
        return this.dealSegments.reduce((sum, seg) => sum + seg.count, 0);
    }

    // Non-empty BL stages with their block size (display share) and real share
    get blSegments() {
        const counts = BL_SEGMENTS.map((seg) => this.state.kpis[seg.kpi] || 0);
        const total = counts.reduce((sum, c) => sum + c, 0);
        if (!total) {
            return [];
        }
        const shares = displayShares(counts);
        return BL_SEGMENTS.map((seg, i) => ({
            ...seg,
            count: counts[i],
            share: shares[i],
            percent: Math.round((counts[i] / total) * 100),
        })).filter((seg) => seg.count);
    }

    get blTotal() {
        return BL_SEGMENTS.reduce((sum, seg) => sum + (this.state.kpis[seg.kpi] || 0), 0);
    }

    get containersTotal() {
        return this.state.containerStates.reduce((sum, p) => sum + p.count, 0);
    }

    /**
     * Containers chart: one column per non-empty parent state, in process
     * order, holding one tile per non-empty child state. Column width comes
     * from CSS (fits the longest label); tile heights follow counts (flex-grow).
     */
    get containerColumns() {
        const total = this.containersTotal;
        return this.state.containerStates
            .filter((p) => p.count)
            .map((p) => ({
                ...p,
                color: this.containerStateColors[p.state],
                title: `${p.label}: ${p.count} (${Math.round((p.count / total) * 100)}%)`,
                children: p.children
                    .filter((c) => c.count)
                    .map((c) => ({
                        ...c,
                        title: `${c.name}: ${c.count} (${Math.round((c.count / p.count) * 100)}% of ${p.label})`,
                    })),
            }));
    }

    renderDealsChart(canvas) {
        this.dealsChart?.destroy();
        const rootStyle = getComputedStyle(document.documentElement);
        const segments = this.dealSegments;
        const colors = segments.map(
            (seg) => rootStyle.getPropertyValue(`--bs-${seg.color}`).trim() || seg.fallback
        );
        const total = this.dealsTotal;
        this.dealsChart = new Chart(canvas, {
            type: "pie",
            data: {
                labels: segments.map((seg) => seg.label),
                datasets: [{
                    // Slices use display shares (small counts enlarged), not raw counts;
                    // with no agreements at all, one grey disc instead of an empty canvas
                    data: total ? displayShares(segments.map((seg) => seg.count)) : [1],
                    backgroundColor: total ? colors : ["#dee2e6"],
                    borderWidth: 1,
                }],
            },
            options: {
                maintainAspectRatio: false,
                layout: { padding: 8 },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: !!total,
                        // Real count and real share, not the enlarged display share
                        callbacks: {
                            label: (item) => {
                                const count = segments[item.dataIndex].count;
                                return ` ${count} (${Math.round((count / total) * 100)}%)`;
                            },
                        },
                    },
                },
                onClick: (_event, elements) => {
                    if (total && elements.length) {
                        this.openDeals(segments[elements[0].index].state);
                    }
                },
                onHover: (event, elements) => {
                    event.native.target.style.cursor = total && elements.length ? "pointer" : "default";
                },
            },
            plugins: total ? [sliceLabelsPlugin(segments, colors)] : [],
        });
    }

    async showMoreArrivals() {
        const data = await this.orm.call("logistics.dashboard", "get_upcoming_arrivals", [
            this.state.upcomingArrivals.length,
        ]);
        this.state.upcomingArrivals.push(...data.lines);
        this.state.upcomingHasMore = data.has_more;
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

    openContainersByChildState(childStateId, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `Containers - ${name}`,
            res_model: "logistics.container",
            views: [[false, "list"], [false, "form"]],
            domain: [["child_state_id", "=", childStateId]],
        });
    }

    // Without arguments, opens all numbered BLs (the total counted on the dashboard)
    openBillLadings(docsDraft, docsOriginal) {
        const domain = [["number", "!=", false], ["number", "!=", ""]];
        if (docsDraft !== undefined) {
            domain.push(["docs_draft", "=", docsDraft], ["docs_original", "=", docsOriginal]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Bills of Lading",
            res_model: "logistics.bill.lading",
            views: [[false, "list"], [false, "form"]],
            domain,
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
