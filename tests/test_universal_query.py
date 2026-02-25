# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestUniversalQuery(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env.user

    def test_planner_validator_orchestrator_roundtrip(self):
        planner = self.env['ai.analyst.query.planner']
        validator = self.env['ai.analyst.query.plan.validator']
        orchestrator = self.env['ai.analyst.query.orchestrator']

        plan = planner.plan(self.user, 'count sale orders by state')
        self.assertTrue(plan.get('steps'))

        verdict = validator.validate(self.user, plan)
        self.assertTrue(verdict['valid'], 'Validation errors: %s' % verdict['errors'])

        payload = orchestrator.run(self.user, plan)
        self.assertIn('steps', payload)

    def test_query_cache(self):
        cache = self.env['ai.analyst.query.cache']
        plan = {'steps': [{'id': 'step_1', 'model': 'res.partner', 'method': 'search_count', 'domain': []}]}
        self.assertFalse(cache.get_cached(plan))
        cache.set_cached(plan, {'ok': True}, ttl_seconds=300)
        self.assertEqual(cache.get_cached(plan), {'ok': True})
