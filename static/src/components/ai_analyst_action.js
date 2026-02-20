/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { WorkspaceSelector } from "../js/workspace_selector";

/**
 * AI Analyst — Main OWL component.
 *
 * This is the chat-first analytics interface. It provides:
 * - Conversation sidebar (past chats)
 * - Chat message list with rich result rendering
 * - KPI cards, data tables, Chart.js charts
 * - Action buttons (download CSV, save report, pin to dashboard)
 * - Chat input with send button
 */
class AiAnalystAction extends Component {
    static template = "ai_analyst.AiAnalystAction";
    static components = { WorkspaceSelector };
    static props = { "*": true };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            conversations: [],
            currentConversationId: null,
            messages: [],
            inputText: "",
            isLoading: false,
            sidebarOpen: true,
            consoleMode: false,
            // Workspace state
            workspaces: [],
            selectedWorkspaceId: null,
            workspacePrompts: [],
            workspaceToolNames: [],
        });

        this.chatContainerRef = useRef("chatContainer");
        this.inputRef = useRef("chatInput");

        // Chart instances for cleanup
        this._chartInstances = {};

        onMounted(() => {
            this.loadConsoleMode();
            this.loadConversations();
            this.loadWorkspaces();
            if (this.inputRef.el) {
                this.inputRef.el.focus();
            }
        });

        onWillUnmount(() => {
            // Destroy all chart instances
            Object.values(this._chartInstances).forEach(chart => {
                if (chart && typeof chart.destroy === "function") {
                    chart.destroy();
                }
            });
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadConsoleMode() {
        try {
            const result = await this.rpc("/ai_analyst/ui/get_console_mode", {});
            this.state.consoleMode = !!result.enabled;
        } catch (e) {
            console.error("Failed to load console mode:", e);
        }
    }

    async toggleConsoleMode(ev) {
        const enabled = !!ev.target.checked;
        this.state.consoleMode = enabled;
        try {
            await this.rpc("/ai_analyst/ui/set_console_mode", { enabled });
        } catch (e) {
            this.state.consoleMode = !enabled;
            console.error("Failed to set console mode:", e);
        }
    }

    async loadConversations() {
        try {
            const result = await this.rpc("/ai_analyst/conversations", {});
            this.state.conversations = result.conversations || [];
        } catch (e) {
            console.error("Failed to load conversations:", e);
        }
    }

    // ------------------------------------------------------------------
    // Workspace loading
    // ------------------------------------------------------------------

    async loadWorkspaces() {
        try {
            const result = await this.rpc("/ai_analyst/workspaces", {});
            this.state.workspaces = result.workspaces || [];
            await this.loadVisibleTools(null);
        } catch (e) {
            console.error("Failed to load workspaces:", e);
        }
    }

    async onWorkspaceSelect(workspaceId) {
        this.state.selectedWorkspaceId = workspaceId;
        if (workspaceId) {
            await this.loadWorkspaceContext(workspaceId);
        } else {
            this.state.workspacePrompts = [];
            await this.loadVisibleTools(null);
        }
        // Start a new conversation when switching workspace
        this.startNewChat();
    }

    async loadWorkspaceContext(workspaceId) {
        try {
            const result = await this.rpc("/ai_analyst/workspace/context", {
                workspace_id: workspaceId,
            });
            if (result.error) {
                console.error("Workspace context error:", result.error);
                this.state.workspacePrompts = [];
                this.state.workspaceToolNames = [];
                return;
            }
            this.state.workspacePrompts = result.prompts || [];
            this.state.workspaceToolNames = result.tool_names || [];
            if (!this.state.workspaceToolNames.length) {
                await this.loadVisibleTools(workspaceId);
            }
        } catch (e) {
            console.error("Failed to load workspace context:", e);
            this.state.workspacePrompts = [];
            this.state.workspaceToolNames = [];
        }
    }

    async loadVisibleTools(workspaceId = null) {
        try {
            const payload = workspaceId ? { workspace_id: workspaceId } : {};
            const result = await this.rpc("/ai_analyst/tools/list", payload);
            this.state.workspaceToolNames = result.tool_names || [];
        } catch (e) {
            console.error("Failed to load tools list:", e);
            this.state.workspaceToolNames = [];
        }
    }

    async loadMessages(conversationId) {
        try {
            const result = await this.rpc("/ai_analyst/conversation/messages", {
                conversation_id: conversationId,
            });
            this.state.messages = result.messages || [];
            this.state.currentConversationId = conversationId;
            this._scrollToBottom();
        } catch (e) {
            console.error("Failed to load messages:", e);
        }
    }

    // ------------------------------------------------------------------
    // Chat interaction
    // ------------------------------------------------------------------

    async sendMessage() {
        const text = this.state.inputText.trim();
        if (!text || this.state.isLoading) return;

        // Add user message optimistically
        this.state.messages.push({
            role: "user",
            content: text,
            create_date: new Date().toISOString(),
        });
        this.state.inputText = "";
        this.state.isLoading = true;
        this._scrollToBottom();

        try {
            const params = {
                conversation_id: this.state.currentConversationId,
                message: text,
            };
            if (this.state.selectedWorkspaceId && !this.state.currentConversationId) {
                params.workspace_id = this.state.selectedWorkspaceId;
            }
            const result = await this.rpc("/ai_analyst/chat", params);

            // Update conversation ID (may be new)
            if (result.conversation_id) {
                this.state.currentConversationId = result.conversation_id;
            }

            // Add assistant message
            this.state.messages.push({
                role: "assistant",
                content: result.answer || "",
                structured_response: result,
                create_date: new Date().toISOString(),
            });

            // Refresh conversation list
            this.loadConversations();
            this._scrollToBottom();

            // Render charts after DOM update
            setTimeout(() => this._renderCharts(), 100);

        } catch (e) {
            console.error("Chat error:", e);
            this.state.messages.push({
                role: "assistant",
                content: "An error occurred. Please try again.",
                structured_response: { error: String(e) },
                create_date: new Date().toISOString(),
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    // ------------------------------------------------------------------
    // Conversation management
    // ------------------------------------------------------------------

    startNewChat() {
        this.state.currentConversationId = null;
        this.state.messages = [];
        if (this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }

    selectConversation(conversationId) {
        this.loadMessages(conversationId);
    }

    async archiveConversation(conversationId) {
        try {
            await this.rpc("/ai_analyst/conversation/archive", {
                conversation_id: conversationId,
            });
            this.loadConversations();
            if (this.state.currentConversationId === conversationId) {
                this.startNewChat();
            }
        } catch (e) {
            console.error("Failed to archive:", e);
        }
    }

    // ------------------------------------------------------------------
    // Actions: Save, Pin, Download
    // ------------------------------------------------------------------

    async saveReport(messageIndex) {
        const msg = this.state.messages[messageIndex];
        if (!msg || !msg.structured_response) return;

        try {
            const result = await this.rpc("/ai_analyst/save_report", {
                conversation_id: this.state.currentConversationId,
                message_id: msg.id || 0,
                name: "",
            });
            if (result.success) {
                this.notification.add("Report saved successfully!", {
                    type: "success",
                });
            }
        } catch (e) {
            this.notification.add("Failed to save report.", { type: "danger" });
        }
    }

    downloadCsv(response) {
        if (!response || !response.actions) return;
        const csvAction = response.actions.find(a => a.type === "download_csv");
        if (csvAction && csvAction.attachment_id) {
            window.open(`/web/content/${csvAction.attachment_id}?download=true`, "_blank");
        }
    }

    // ------------------------------------------------------------------
    // Chart rendering
    // ------------------------------------------------------------------

    _renderCharts() {
        const containers = document.querySelectorAll("[data-chart-index]");
        containers.forEach(container => {
            const index = container.dataset.chartIndex;
            const msg = this.state.messages[index];
            if (!msg || !msg.structured_response || !msg.structured_response.chart) return;

            const chartData = msg.structured_response.chart;
            const canvas = container.querySelector("canvas");
            if (!canvas) return;

            // Destroy existing chart if any
            if (this._chartInstances[index]) {
                this._chartInstances[index].destroy();
            }

            const colors = [
                "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
                "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
                "#9c755f", "#bab0ac",
            ];

            const datasets = (chartData.datasets || []).map((ds, i) => ({
                label: ds.label || `Dataset ${i + 1}`,
                data: ds.data || [],
                backgroundColor: ds.color || colors[i % colors.length],
                borderColor: ds.color || colors[i % colors.length],
                borderWidth: chartData.type === "line" ? 2 : 1,
                fill: false,
            }));

            try {
                // Chart is loaded as global from Chart.js CDN/asset
                const ChartJS = window.Chart;
                if (!ChartJS) {
                    console.warn("Chart.js not loaded");
                    return;
                }

                this._chartInstances[index] = new ChartJS(canvas, {
                    type: chartData.type === "stacked_bar" ? "bar" : (chartData.type || "bar"),
                    data: {
                        labels: chartData.labels || [],
                        datasets: datasets,
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            title: {
                                display: !!chartData.title,
                                text: chartData.title || "",
                            },
                            legend: {
                                display: datasets.length > 1,
                            },
                        },
                        scales: chartData.type === "pie" || chartData.type === "doughnut" ? {} : {
                            x: {
                                stacked: chartData.type === "stacked_bar",
                            },
                            y: {
                                stacked: chartData.type === "stacked_bar",
                                beginAtZero: true,
                            },
                        },
                    },
                });
            } catch (e) {
                console.error("Failed to render chart:", e);
            }
        });
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    _scrollToBottom() {
        setTimeout(() => {
            const container = this.chatContainerRef.el;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 50);
    }

    formatTime(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleDateString();
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
    }

    get hasKpis() {
        return (msg) => msg.structured_response && msg.structured_response.kpis &&
            msg.structured_response.kpis.length > 0;
    }

    get hasTable() {
        return (msg) => msg.structured_response && msg.structured_response.table &&
            msg.structured_response.table.columns;
    }

    get hasChart() {
        return (msg) => msg.structured_response && msg.structured_response.chart;
    }
}

// Register as action client
registry.category("actions").add("ai_analyst_main", AiAnalystAction);
