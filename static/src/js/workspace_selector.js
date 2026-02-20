/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * WorkspaceSelector — Dropdown component for switching workspaces.
 *
 * Props:
 *   workspaces: Array<{id, name, code, icon, color}>
 *   selectedWorkspaceId: number|null
 *   onSelect: function(workspaceId: number|null)
 */
export class WorkspaceSelector extends Component {
    static template = "ai_analyst.WorkspaceSelector";
    static props = {
        workspaces: { type: Array },
        selectedWorkspaceId: { type: [Number, { value: null }], optional: true },
        toolNames: { type: Array, optional: true },
        onSelect: { type: Function },
    };

    get currentWorkspace() {
        if (!this.props.selectedWorkspaceId) return null;
        return this.props.workspaces.find(ws => ws.id === this.props.selectedWorkspaceId) || null;
    }

    selectWorkspace(workspaceId) {
        this.props.onSelect(workspaceId);
    }
}
