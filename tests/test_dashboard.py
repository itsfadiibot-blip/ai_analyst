# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError

from odoo.addons.ai_analyst.tools.registry import TOOL_REGISTRY
from odoo.addons.ai_analyst.tools.base_tool import BaseTool


class _FakeDashboardTool(BaseTool):
    name = 'test_dashboard_tool'
    description = 'Test tool'
    parameters_schema = {
        'type': 'object',
        'properties': {'seed': {'type': 'integer'}},
    }
    _counter = 0

    def execute(self, env, user, params):
        _FakeDashboardTool._counter += 1
        return {
            'answer': f"Run {_FakeDashboardTool._counter}",
            'kpis': [{'label': 'Counter', 'value': str(_FakeDashboardTool._counter)}],
            'meta': {'tool_calls': [{'tool': self.name, 'params': params}]},
        }


@tagged('post_install', '-at_install')
class TestDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_1 = cls.env['res.users'].create({
            'name': 'Dash User 1',
            'login': 'dash_user_1',
            'email': 'dash1@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })
        cls.user_2 = cls.env['res.users'].create({
            'name': 'Dash User 2',
            'login': 'dash_user_2',
            'email': 'dash2@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })

        cls._old_tool = TOOL_REGISTRY.get('test_dashboard_tool')
        TOOL_REGISTRY['test_dashboard_tool'] = _FakeDashboardTool()

    @classmethod
    def tearDownClass(cls):
        if cls._old_tool is None:
            TOOL_REGISTRY.pop('test_dashboard_tool', None)
        else:
            TOOL_REGISTRY['test_dashboard_tool'] = cls._old_tool
        super().tearDownClass()

    def _create_widget(self, user):
        dashboard = self.env['ai.analyst.dashboard'].with_user(user).get_or_create_default(user)
        return self.env['ai.analyst.dashboard.widget'].with_user(user).create({
            'dashboard_id': dashboard.id,
            'user_id': user.id,
            'company_id': user.company_id.id,
            'tool_name': 'test_dashboard_tool',
            'tool_args_json': '{"seed": 1}',
            'title': 'Test Widget',
        })

    def test_dashboard_widget_execution(self):
        widget = self._create_widget(self.user_1)
        result = widget.with_user(self.user_1).execute_dynamic(user=self.user_1, bypass_cache=True)
        self.assertIn('answer', result)
        self.assertIn('kpis', result)
        self.assertEqual(result['meta']['tool_calls'][0]['tool'], 'test_dashboard_tool')

    def test_dashboard_security(self):
        widget = self._create_widget(self.user_1)
        with self.assertRaises(AccessError):
            widget.with_user(self.user_2).execute_dynamic(user=self.user_2, bypass_cache=True)

    def test_dynamic_refresh(self):
        widget = self._create_widget(self.user_1)
        r1 = widget.with_user(self.user_1).execute_dynamic(user=self.user_1, bypass_cache=True)
        r2 = widget.with_user(self.user_1).execute_dynamic(user=self.user_1, bypass_cache=True)
        self.assertNotEqual(r1.get('answer'), r2.get('answer'))
