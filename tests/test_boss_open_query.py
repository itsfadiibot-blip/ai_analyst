# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestBossOpenQuery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_ai_user = cls.env.ref('ai_analyst.group_ai_user')
        cls.group_boss = cls.env.ref('ai_analyst.group_boss_open_query')

        cls.normal_user = cls.env['res.users'].create({
            'name': 'Normal AI User',
            'login': 'normal_ai_user_boq',
            'email': 'normal_boq@test.com',
            'groups_id': [(6, 0, [cls.group_ai_user.id])],
        })
        sale_manager = cls.env.ref('sales_team.group_sale_manager', raise_if_not_found=False)
        boss_groups = [cls.group_ai_user.id, cls.group_boss.id]
        if sale_manager:
            boss_groups.append(sale_manager.id)

        cls.boss_user = cls.env['res.users'].create({
            'name': 'Boss AI User',
            'login': 'boss_ai_user_boq',
            'email': 'boss_boq@test.com',
            'groups_id': [(6, 0, boss_groups)],
        })

        partner = cls.env['res.partner'].create({'name': 'BOQ Partner'})
        product = cls.env['product.product'].create({'name': 'BOQ Product', 'list_price': 100.0, 'type': 'consu'})
        today = date.today()
        for i in range(8):
            order = cls.env['sale.order'].create({
                'partner_id': partner.id,
                'company_id': cls.boss_user.company_id.id,
                'date_order': today - timedelta(days=i),
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 1,
                    'price_unit': 100.0 + i,
                })],
            })
            order.action_confirm()

    def _base_plan(self):
        return {
            'version': '1.0',
            'target_model': 'sale.order',
            'domain': [('state', 'in', ['sale', 'done'])],
            'fields': [{'name': 'name'}, {'name': 'amount_total'}],
            'pagination': {'mode': 'offset', 'limit': 5, 'offset': 0},
        }

    def test_boss_only_access(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('boss_open_query')
        self.assertTrue(tool.check_access(self.boss_user))
        self.assertFalse(tool.check_access(self.normal_user))

        with self.assertRaises(AccessError):
            tool.execute(self.env(user=self.normal_user.id), self.normal_user, {'query_plan': self._base_plan(), 'mode': 'inline'})

    def test_plan_validation_and_execution(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('boss_open_query')

        with self.assertRaises(ValidationError):
            tool.execute(self.env(user=self.boss_user.id), self.boss_user, {
                'query_plan': {'version': '1.0', 'target_model': 'sale.order', 'pagination': {'mode': 'offset', 'limit': 100, 'offset': 0}, 'fields': [{'name': 'not_a_real_field'}]},
                'mode': 'inline',
            })

        result = tool.execute(self.env(user=self.boss_user.id), self.boss_user, {'query_plan': self._base_plan(), 'mode': 'paginated'})
        self.assertEqual(set(result.keys()), {'answer', 'kpis', 'table', 'chart', 'actions', 'meta'})
        self.assertIn('rows', result['table'])
        self.assertLessEqual(len(result['table']['rows']), 5)

    def test_async_export_flow(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('boss_open_query')
        result = tool.execute(self.env(user=self.boss_user.id), self.boss_user, {'query_plan': self._base_plan(), 'mode': 'async_export'})

        self.assertIn('export_job_id', result['meta'])
        job = self.env['ai.analyst.boss.export.job'].browse(result['meta']['export_job_id'])
        self.assertTrue(job.exists())
        job.action_process()
        self.assertEqual(job.state, 'completed')
        self.assertTrue(job.csv_content)

    def test_saved_report_and_dashboard_rerun(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('boss_open_query')
        args = {'query_plan': self._base_plan(), 'mode': 'inline'}
        raw = tool.execute(self.env(user=self.boss_user.id), self.boss_user, args)

        report = self.env['ai.analyst.saved.report'].with_user(self.boss_user).create({
            'name': 'Boss Query Report',
            'tool_name': 'boss_open_query',
            'tool_args_json': '{"query_plan": {"version": "1.0", "target_model": "sale.order", "domain": [["state", "in", ["sale", "done"]]], "fields": [{"name": "name"}, {"name": "amount_total"}], "pagination": {"mode": "offset", "limit": 5, "offset": 0}}, "mode": "inline"}',
            'user_id': self.boss_user.id,
            'company_id': self.boss_user.company_id.id,
            'structured_response': '{}',
        })
        self.assertEqual(report.tool_name, 'boss_open_query')

        dashboard = self.env['ai.analyst.dashboard'].with_user(self.boss_user).get_or_create_default(self.boss_user)
        widget = self.env['ai.analyst.dashboard.widget'].with_user(self.boss_user).create({
            'dashboard_id': dashboard.id,
            'user_id': self.boss_user.id,
            'company_id': self.boss_user.company_id.id,
            'tool_name': report.tool_name,
            'tool_args_json': report.tool_args_json,
            'title': 'BOQ Widget',
        })
        rerun = widget.execute_dynamic(user=self.boss_user, bypass_cache=True)
        self.assertIn('answer', rerun)
        self.assertIn('table', rerun)
        self.assertTrue(raw['table']['rows'])
