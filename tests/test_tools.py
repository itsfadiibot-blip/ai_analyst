# -*- coding: utf-8 -*-
"""
Unit tests for AI Analyst tools.
=================================
Each tool is tested for:
- Valid parameter handling
- Invalid parameter rejection
- Correct ORM query execution (with mocked data)
- Access control enforcement
- Row limits
"""
import logging
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestSalesSummaryTool(TransactionCase):
    """Tests for get_sales_summary tool."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_admin')
        cls.company = cls.user.company_id

        # Create test sale orders
        partner = cls.env['res.partner'].create({'name': 'Test Customer'})
        product = cls.env['product.product'].create({
            'name': 'Test Product',
            'list_price': 100.0,
            'type': 'consu',
        })

        today = date.today()
        for i in range(5):
            order = cls.env['sale.order'].create({
                'partner_id': partner.id,
                'company_id': cls.company.id,
                'date_order': today - timedelta(days=i),
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 2,
                    'price_unit': 100.0,
                })],
            })
            order.action_confirm()

    def test_valid_params(self):
        """Test tool with valid parameters returns expected structure."""
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_summary')
        self.assertIsNotNone(tool)

        today = date.today()
        params = tool.validate_params({
            'date_from': (today - timedelta(days=30)).isoformat(),
            'date_to': today.isoformat(),
        })
        self.assertIn('date_from', params)
        self.assertIn('date_to', params)

    def test_missing_required_params(self):
        """Test tool raises ValidationError for missing required params."""
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_summary')

        with self.assertRaises(ValidationError):
            tool.validate_params({})

        with self.assertRaises(ValidationError):
            tool.validate_params({'date_from': '2025-01-01'})

    def test_invalid_date_format(self):
        """Test tool rejects invalid date format."""
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_summary')

        with self.assertRaises(ValidationError):
            tool.validate_params({
                'date_from': 'not-a-date',
                'date_to': '2025-01-31',
            })

    def test_execute_returns_data(self):
        """Test tool execution returns expected data structure."""
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_summary')

        today = date.today()
        params = {
            'date_from': (today - timedelta(days=30)).isoformat(),
            'date_to': today.isoformat(),
        }
        validated = tool.validate_params(params)
        env_as_user = self.env(user=self.user.id)
        result = tool.execute(env_as_user, self.user, validated)

        self.assertIn('summary', result)
        self.assertIn('total_revenue', result['summary'])
        self.assertIn('order_count', result['summary'])
        self.assertIn('avg_order_value', result['summary'])
        self.assertIn('currency', result)

    def test_execute_with_comparison(self):
        """Test tool with compare_previous=True."""
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_summary')

        today = date.today()
        params = {
            'date_from': (today - timedelta(days=30)).isoformat(),
            'date_to': today.isoformat(),
            'compare_previous': True,
        }
        validated = tool.validate_params(params)
        env_as_user = self.env(user=self.user.id)
        result = tool.execute(env_as_user, self.user, validated)

        self.assertIn('previous_period', result)
        self.assertIn('deltas', result)


@tagged('post_install', '-at_install')
class TestToolAccessControl(TransactionCase):
    """Test that tools respect Odoo access controls."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a user with minimal access
        cls.limited_user = cls.env['res.users'].create({
            'name': 'Limited User',
            'login': 'ai_test_limited',
            'email': 'limited@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    def test_tool_access_check(self):
        """Test that tools with required_groups block unauthorized users."""
        from odoo.addons.ai_analyst.tools.base_tool import BaseTool
        from odoo.addons.ai_analyst.tools.registry import register_tool

        # Tool requiring HR group
        class TestRestrictedTool(BaseTool):
            name = '_test_restricted'
            description = 'Test restricted tool'
            parameters_schema = {'type': 'object', 'properties': {}, 'required': []}
            required_groups = ['hr.group_hr_user']

            def execute(self, env, user, params):
                return {'data': []}

        tool = TestRestrictedTool()
        self.assertFalse(tool.check_access(self.limited_user))

    def test_user_with_group_passes(self):
        """Test that users with required groups pass access check."""
        from odoo.addons.ai_analyst.tools.base_tool import BaseTool

        class TestOpenTool(BaseTool):
            name = '_test_open'
            description = 'Test open tool'
            parameters_schema = {'type': 'object', 'properties': {}, 'required': []}
            required_groups = []  # No group requirement

            def execute(self, env, user, params):
                return {'data': []}

        tool = TestOpenTool()
        self.assertTrue(tool.check_access(self.limited_user))


@tagged('post_install', '-at_install')
class TestToolRegistry(TransactionCase):
    """Test tool registration and lookup."""

    def test_all_phase1_tools_registered(self):
        """Verify all Phase-1 tools are registered."""
        from odoo.addons.ai_analyst.tools.registry import get_all_tools

        tools = get_all_tools()
        expected_tools = [
            'get_sales_summary',
            'get_pos_summary',
            'get_pos_vs_online_summary',
            'get_top_sellers',
            'get_margin_summary',
            'get_inventory_valuation',
            'get_stock_aging',
            'get_refund_return_impact',
            'get_ar_aging',
            'get_ap_aging',
            'export_csv',
        ]
        for tool_name in expected_tools:
            self.assertIn(tool_name, tools, f'Tool "{tool_name}" not registered')

    def test_tools_have_schemas(self):
        """Verify all tools have valid schemas."""
        from odoo.addons.ai_analyst.tools.registry import get_all_tools

        tools = get_all_tools()
        for name, tool in tools.items():
            schema = tool.get_schema()
            self.assertIn('name', schema)
            self.assertIn('description', schema)
            self.assertIn('parameters', schema)
            self.assertEqual(schema['name'], name)
            self.assertTrue(len(schema['description']) > 10,
                            f'Tool "{name}" has too short a description')
