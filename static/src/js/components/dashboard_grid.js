/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DashboardGrid extends Component {
    static template = "ai_analyst.DashboardGrid";
    static props = { widgets: Array, reload: Function };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.state = useState({
            results: {},
            loading: {},
        });
        this._timers = {};
        this._chartInstances = {};

        onMounted(() => {
            (this.props.widgets || []).forEach((w) => {
                this.refreshWidget(w.id);
                if ((w.refresh_interval_seconds || 0) > 0) {
                    this._timers[w.id] = setInterval(() => this.refreshWidget(w.id), w.refresh_interval_seconds * 1000);
                }
            });
        });

        onWillUnmount(() => {
            Object.values(this._timers).forEach((t) => clearInterval(t));
            Object.values(this._chartInstances).forEach((c) => c?.destroy?.());
        });
    }

    async refreshWidget(widgetId, force = false) {
        if (this.state.loading[widgetId]) return;
        this.state.loading[widgetId] = true;
        try {
            const res = await this.rpc("/ai_analyst/dashboard/run_widget", { widget_id: widgetId, force });
            if (res.error) {
                this.state.results[widgetId] = { error: res.error, answer: res.error };
            } else {
                this.state.results[widgetId] = res.result || {};
                setTimeout(() => this._renderChart(widgetId), 20);
            }
        } catch (e) {
            this.state.results[widgetId] = { error: "Refresh failed", answer: "Refresh failed" };
        } finally {
            this.state.loading[widgetId] = false;
        }
    }

    async removeWidget(widgetId) {
        await this.rpc("/ai_analyst/dashboard/widget/remove", { widget_id: widgetId });
        await this.props.reload();
    }

    async editTitle(widgetId) {
        const title = window.prompt("New widget title:");
        if (!title) return;
        await this.rpc("/ai_analyst/dashboard/widget/update", { widget_id: widgetId, values: { title } });
        await this.props.reload();
    }

    _renderChart(widgetId) {
        const result = this.state.results[widgetId];
        const chart = result?.chart;
        if (!chart) return;
        const canvas = document.querySelector(`[data-widget-chart='${widgetId}'] canvas`);
        if (!canvas || !window.Chart) return;
        if (this._chartInstances[widgetId]) {
            this._chartInstances[widgetId].destroy();
        }
        this._chartInstances[widgetId] = new window.Chart(canvas, {
            type: chart.type === "stacked_bar" ? "bar" : (chart.type || "bar"),
            data: {
                labels: chart.labels || [],
                datasets: (chart.datasets || []).map((d) => ({
                    label: d.label,
                    data: d.data || [],
                    backgroundColor: d.color,
                    borderColor: d.color,
                    borderWidth: 1,
                })),
            },
            options: { responsive: true, maintainAspectRatio: false },
        });
    }
}
