# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDimensionTools(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_admin')

        # Ensure dimensions exist for test isolation
        cls.dim_gender = cls.env['ai.analyst.dimension'].create({
            'name': 'Gender',
            'code': 'gender_test',
            'model_name': 'sale.order.line',
            'field_name': 'product_id.product_tmpl_id.name',
            'company_id': cls.user.company_id.id,
        })
        cls.env['ai.analyst.dimension.synonym'].create({
            'dimension_id': cls.dim_gender.id,
            'synonym': 'women',
            'canonical_value': 'Women',
            'match_type': 'contains',
            'priority': 1,
        })

        cls.dim_category = cls.env['ai.analyst.dimension'].create({
            'name': 'Category',
            'code': 'category_test',
            'model_name': 'sale.order.line',
            'field_name': 'product_id.categ_id.name',
            'company_id': cls.user.company_id.id,
        })
        cls.env['ai.analyst.dimension.synonym'].create({
            'dimension_id': cls.dim_category.id,
            'synonym': 'sneakers',
            'canonical_value': 'Shoes',
            'match_type': 'contains',
            'priority': 1,
        })

        # Season configuration for pattern matching
        cls.dim_season = cls.env['ai.analyst.dimension'].create({
            'name': 'Season',
            'code': 'season',
            'model_name': 'sale.order.line',
            'field_name': 'product_id.product_tmpl_id.default_code',
            'company_id': cls.user.company_id.id,
        })
        cls.season_fw25 = cls.env['ai.analyst.season.config'].create({
            'name': 'Fall/Winter 2025',
            'code': 'FW25',
            'company_id': cls.user.company_id.id,
        })
        cls.env['ai.analyst.season.tag.pattern'].create({
            'season_config_id': cls.season_fw25.id,
            'pattern': 'AW25',
            'match_type': 'exact',
        })

        cls.season_fw24 = cls.env['ai.analyst.season.config'].create({
            'name': 'Fall/Winter 2024',
            'code': 'FW24',
            'company_id': cls.user.company_id.id,
        })
        cls.env['ai.analyst.season.tag.pattern'].create({
            'season_config_id': cls.season_fw24.id,
            'pattern': 'AW24',
            'match_type': 'exact',
        })

        # Sales data
        categ = cls.env['product.category'].create({'name': 'Shoes'})
        product = cls.env['product.product'].create({
            'name': 'Women AW25 Sneakers Red',
            'default_code': 'AW25',
            'type': 'consu',
            'categ_id': categ.id,
            'list_price': 100.0,
        })
        partner = cls.env['res.partner'].create({'name': 'Dimension Customer'})

        order = cls.env['sale.order'].create({
            'partner_id': partner.id,
            'company_id': cls.user.company_id.id,
            'date_order': date.today() - timedelta(days=5),
            'order_line': [(0, 0, {
                'product_id': product.id,
                'product_uom_qty': 2,
                'price_unit': 100.0,
            })],
        })
        order.action_confirm()

    def test_synonym_resolution(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_by_dimension')
        resolved = tool._resolve_synonym(
            self.env.with_user(self.user), self.dim_gender, "women's"
        )
        self.assertEqual(resolved, 'Women')

    def test_season_pattern_matching(self):
        season = self.env['ai.analyst.season.config'].find_by_tag('AW25')
        self.assertTrue(season)
        self.assertEqual(season.code, 'FW25')

    def test_dimension_grouping_returns_data(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        tool = get_tool('get_sales_by_dimension')
        params = {
            'date_from': (date.today() - timedelta(days=30)).isoformat(),
            'date_to': date.today().isoformat(),
            'dimension_codes': ['category_test'],
            'filters': {'category_test': 'sneakers'},
        }
        result = tool.execute(self.env.with_user(self.user), self.user, params)
        self.assertIn('rows', result)
        self.assertGreaterEqual(len(result['rows']), 1)
