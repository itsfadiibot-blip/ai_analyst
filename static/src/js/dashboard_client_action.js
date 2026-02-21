/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class AiAnalystDashboardAction extends Component {
    static template = "ai_analyst.AiAnalystDashboardAction";
    static props = { "*": true };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");

        this.state = useState({
            dashboard: null,
            widgets: [],
            loading: true,
            results: {},
            widgetLoading: {},
        });
        this._timers = {};
        this._chartInstances = {};

        onMounted(async () => {
            await this.load();
        });
        onWillUnmount(() => {
            Object.values(this._timers).forEach((t) => clearInterval(t));
            Object.values(this._chartInstances).forEach((c) => c?.destroy?.());
        });
    }

    async load() {
        this.state.loading = true;
        try {
            const res = await this.rpc("/ai_analyst/dashboard/list", {});
            if (res.error) {
                this.notification.add(res.error, { type: "danger" });
                return;
            }
            this.state.dashboard = res.dashboard;
            this.state.widgets = res.widgets || [];

            Object.values(this._timers).forEach((t) => clearInterval(t));
            this._timers = {};

            for (const w of this.state.widgets) {
                this.refreshWidget(w.id, false);
                if ((w.refresh_interval_seconds || 0) > 0) {
                    this._timers[w.id] = setInterval(() => this.refreshWidget(w.id, false), w.refresh_interval_seconds * 1000);
                }
            }
        } catch (e) {
            this.notification.add("Failed to load dashboard.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async refreshWidget(widgetId, force = true) {
        if (this.state.widgetLoading[widgetId]) return;
        this.state.widgetLoading[widgetId] = true;
        try {
            const res = await this.rpc("/ai_analyst/dashboard/run_widget", { widget_id: widgetId, force });
            if (res.error) {
                this.state.results[widgetId] = { error: res.error, answer: res.error };
            } else {
                this.state.results[widgetId] = res.result || {};
                setTimeout(() => this._renderChart(widgetId), 30);
            }
        } finally {
            this.state.widgetLoading[widgetId] = false;
        }
    }

    async removeWidget(widgetId) {
        await this.rpc("/ai_analyst/dashboard/widget/remove", { widget_id: widgetId });
        await this.load();
    }

    async editTitle(widgetId) {
        const title = window.prompt("New widget title:");
        if (!title) return;
        await this.rpc("/ai_analyst/dashboard/widget/update", { widget_id: widgetId, values: { title } });
        await this.load();
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

registry.category("actions").add("ai_analyst_dashboard", AiAnalystDashboardAction);
