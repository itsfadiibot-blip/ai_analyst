# -*- coding: utf-8 -*-
import json
import threading

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_MAX_PARALLEL_WIDGET_RUNS = 10
_WIDGET_SEMAPHORE = threading.BoundedSemaphore(_MAX_PARALLEL_WIDGET_RUNS)


class AiAnalystDashboardController(http.Controller):

    @http.route('/ai_analyst/dashboard/list', type='json', auth='user', methods=['POST'])
    def dashboard_list(self, dashboard_id=None, **kwargs):
        user = request.env.user
        Dashboard = request.env['ai.analyst.dashboard'].with_user(user.id)
        if dashboard_id:
            dashboard = Dashboard.browse(int(dashboard_id))
            if not dashboard.exists():
                return {'error': 'Dashboard not found.'}
            if dashboard.user_id.id != user.id and not user.has_group('ai_analyst.group_ai_admin'):
                return {'error': 'Access denied.'}
        else:
            dashboard = Dashboard.get_or_create_default(user)

        # Backfill: ensure previously pinned reports appear as dashboard widgets.
        # This heals older records pinned before widget-link automation was added.
        reports_to_pin = request.env['ai.analyst.saved.report'].with_user(user.id).search([
            ('user_id', '=', user.id),
            ('company_id', '=', user.company_id.id),
            ('is_pinned', '=', True),
            ('tool_name', '!=', False),
            ('pinned_widget_id', '=', False),
        ], limit=50)
        for report in reports_to_pin:
            try:
                report._ensure_pinned_widget()
            except Exception:
                # Keep dashboard usable even if one report cannot be re-pinned.
                continue

        data = dashboard.read(['id', 'name', 'is_default', 'user_id', 'company_id'])[0]
        widgets = request.env['ai.analyst.dashboard.widget'].with_user(user.id).search_read(
            [('dashboard_id', '=', dashboard.id), ('active', '=', True)],
            fields=['id', 'title', 'sequence', 'width', 'height', 'refresh_interval_seconds', 'last_run_at', 'tool_name'],
            order='sequence asc, id asc',
        )
        return {'dashboard': data, 'widgets': widgets}

    @http.route('/ai_analyst/dashboard/run_widget', type='json', auth='user', methods=['POST'])
    def run_widget(self, widget_id, force=False, **kwargs):
        user = request.env.user
        widget = request.env['ai.analyst.dashboard.widget'].with_user(user.id).browse(int(widget_id))
        if not widget.exists():
            return {'error': 'Widget not found.'}
        if widget.user_id.id != user.id and not user.has_group('ai_analyst.group_ai_admin'):
            return {'error': 'Access denied.'}

        acquired = _WIDGET_SEMAPHORE.acquire(timeout=10)
        if not acquired:
            return {'error': 'Too many widget refreshes in progress. Try again in a moment.'}

        try:
            result = widget.execute_dynamic(user=user, bypass_cache=bool(force))
            return {
                'widget_id': widget.id,
                'result': result,
            }
        except AccessError as e:
            return {'error': str(e)}
        except Exception as e:
            return {'error': str(e)}
        finally:
            _WIDGET_SEMAPHORE.release()

    @http.route('/ai_analyst/dashboard/widget/update', type='json', auth='user', methods=['POST'])
    def update_widget(self, widget_id, values=None, **kwargs):
        user = request.env.user
        values = values or {}
        widget = request.env['ai.analyst.dashboard.widget'].with_user(user.id).browse(int(widget_id))
        if not widget.exists():
            return {'error': 'Widget not found.'}
        if widget.user_id.id != user.id and not user.has_group('ai_analyst.group_ai_admin'):
            return {'error': 'Access denied.'}

        allowed = {'title', 'sequence', 'width', 'height', 'refresh_interval_seconds', 'active'}
        vals = {k: v for k, v in values.items() if k in allowed}
        if not vals:
            return {'success': True}
        widget.with_user(user.id).write(vals)
        return {'success': True}

    @http.route('/ai_analyst/dashboard/widget/remove', type='json', auth='user', methods=['POST'])
    def remove_widget(self, widget_id, **kwargs):
        user = request.env.user
        widget = request.env['ai.analyst.dashboard.widget'].with_user(user.id).browse(int(widget_id))
        if not widget.exists():
            return {'error': 'Widget not found.'}
        if widget.user_id.id != user.id and not user.has_group('ai_analyst.group_ai_admin'):
            return {'error': 'Access denied.'}
        widget.with_user(user.id).unlink()
        return {'success': True}

