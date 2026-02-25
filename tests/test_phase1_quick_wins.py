# -*- coding: utf-8 -*-
"""
Phase 1 Implementation Tests
============================

Unit tests for Phase 1 (Quick Wins) of the AI Analyst architecture redesign:

1. Fix Bug #4: with_user(user) → with_user(user.id) in query_orchestrator.py
2. Fix CSV download in controllers/main.py (JS fix)
3. Add mandatory Response Schema validation in gateway
4. Fix dashboard widget refresh intervals (default 0 → 300)
5. Add computed field rejection in validator

"""
import json
from odoo.tests import common, tagged
from odoo.exceptions import AccessError


@tagged('ai_analyst', 'phase1', 'post_install', '-at_install')
class TestPhase1QuickWins(common.TransactionCase):
    """Test suite for Phase 1 Quick Wins implementation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.user
        cls.company = cls.user.company_id
        
        # Create test conversation
        cls.conversation = cls.env['ai.analyst.conversation'].create({
            'user_id': cls.user.id,
            'company_id': cls.company.id,
        })

    # =================================================================
    # Test 1: Bug #4 - with_user(user) → with_user(user.id)
    # =================================================================
    
    def test_01_query_orchestrator_with_user_id(self):
        """Bug #4: Verify orchestrator uses user.id (int) instead of user recordset."""
        orchestrator = self.env['ai.analyst.query.orchestrator']
        
        # Create a simple test plan
        plan = {
            'steps': [{
                'id': 'step1',
                'model': 'res.users',
                'method': 'search_count',
                'domain': [('id', '=', self.user.id)],
            }]
        }
        
        # This should work with user.id (int) not user (recordset)
        result = orchestrator.run(self.user, plan)
        
        self.assertIn('steps', result)
        self.assertIn('step1', result['steps'])
        self.assertEqual(result['steps']['step1']['count'], 1)
    
    def test_01b_query_orchestrator_with_user_as_int(self):
        """Bug #4: Verify orchestrator works when user is passed as integer ID."""
        orchestrator = self.env['ai.analyst.query.orchestrator']
        
        plan = {
            'steps': [{
                'id': 'step1',
                'model': 'res.users',
                'method': 'search_count',
                'domain': [('id', '=', self.user.id)],
            }]
        }
        
        # Should work with integer user ID
        result = orchestrator.run(self.user.id, plan)
        
        self.assertIn('steps', result)
        self.assertIn('step1', result['steps'])

    # =================================================================
    # Test 2: Response Schema Validation in Gateway
    # =================================================================
    
    def test_02_response_schema_validation_valid(self):
        """Bug #12: Verify valid responses pass schema validation."""
        gateway = self.env['ai.analyst.gateway']
        
        valid_response = {
            'answer': 'Test answer',
            'kpis': [{'label': 'Test', 'value': '123'}],
            'table': {
                'columns': [{'key': 'name', 'label': 'Name', 'type': 'string'}],
                'rows': [{'name': 'Test'}],
            },
            'actions': [{'type': 'download_csv', 'label': 'Download'}],
        }
        
        is_valid, errors = gateway._validate_response_schema(valid_response)
        self.assertTrue(is_valid, f"Valid response failed validation: {errors}")
        self.assertEqual(len(errors), 0)
    
    def test_02b_response_schema_validation_missing_answer(self):
        """Bug #12: Verify responses without 'answer' fail validation."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'table': {
                'columns': [{'key': 'name', 'label': 'Name', 'type': 'string'}],
                'rows': [],
            }
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing required field: 'answer'" in e for e in errors))
    
    def test_02c_response_schema_validation_empty_answer(self):
        """Bug #12: Verify responses with empty answer fail validation."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'answer': '',
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("must not be empty" in e for e in errors))
    
    def test_02d_response_schema_validation_extra_keys(self):
        """Bug #12: Verify responses with extra top-level keys fail validation."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'answer': 'Test',
            'invalid_key': 'should not be allowed',
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("Unexpected top-level keys" in e for e in errors))
    
    def test_02e_response_schema_validation_ensure_valid(self):
        """Bug #12: Verify _ensure_valid_response returns valid response."""
        gateway = self.env['ai.analyst.gateway']
        
        # Test with invalid response - should return sanitized error response
        invalid_response = {'invalid_key': 'value'}
        result = gateway._ensure_valid_response(invalid_response)
        
        # Should have answer and meta with validation_errors
        self.assertIn('answer', result)
        self.assertIn('meta', result)
        self.assertIn('validation_errors', result['meta'])
    
    def test_02f_response_schema_validation_invalid_kpi(self):
        """Bug #12: Verify invalid KPI structure is caught."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'answer': 'Test',
            'kpis': [{'invalid': 'missing label and value'}],
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("missing required 'label' or 'value'" in e for e in errors))
    
    def test_02g_response_schema_validation_invalid_table(self):
        """Bug #12: Verify invalid table structure is caught."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'answer': 'Test',
            'table': {'rows': []},  # Missing columns
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("missing required 'columns'" in e for e in errors))
    
    def test_02h_response_schema_validation_invalid_action_type(self):
        """Bug #12: Verify invalid action type is caught."""
        gateway = self.env['ai.analyst.gateway']
        
        invalid_response = {
            'answer': 'Test',
            'actions': [{'type': 'invalid_action', 'label': 'Test'}],
        }
        
        is_valid, errors = gateway._validate_response_schema(invalid_response)
        self.assertFalse(is_valid)
        self.assertTrue(any("has invalid type" in e for e in errors))

    # =================================================================
    # Test 3: Dashboard Widget Refresh Interval Default
    # =================================================================
    
    def test_03_dashboard_widget_refresh_default(self):
        """Bug #6: Verify new widgets have default refresh_interval_seconds=300."""
        # Create a dashboard
        dashboard = self.env['ai.analyst.dashboard'].create({
            'name': 'Test Dashboard',
            'user_id': self.user.id,
            'company_id': self.company.id,
        })
        
        # Create a widget (simulating the pin_to_dashboard flow)
        widget = self.env['ai.analyst.dashboard.widget'].create({
            'dashboard_id': dashboard.id,
            'user_id': self.user.id,
            'company_id': self.company.id,
            'tool_name': 'test_tool',
            'tool_args_json': '{}',
            'title': 'Test Widget',
        })
        
        # Verify default is 300 (5 minutes), not 0
        self.assertEqual(widget.refresh_interval_seconds, 300,
            "Widget refresh_interval_seconds should default to 300 (5 minutes)")

    # =================================================================
    # Test 4: Computed Field Rejection in Validator
    # =================================================================
    
    def test_04_validator_rejects_computed_in_domain(self):
        """Bug #11: Verify validator rejects computed fields in domain filters."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        # Create a plan with computed field in domain
        # Using qty_available on product.product which is computed
        plan = {
            'steps': [{
                'model': 'product.product',
                'domain': [('qty_available', '>', 0)],  # qty_available is computed
            }]
        }
        
        result = validator.validate(self.user, plan)
        
        self.assertFalse(result['valid'])
        self.assertTrue(any('computed' in e.lower() and 'qty_available' in e.lower() 
                           for e in result['errors']),
            f"Should reject computed field in domain. Errors: {result['errors']}")
    
    def test_04b_validator_rejects_computed_in_fields(self):
        """Bug #11: Verify validator rejects computed fields in fields selection."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        plan = {
            'steps': [{
                'model': 'product.product',
                'fields': ['name', 'qty_available'],  # qty_available is computed
                'domain': [],
            }]
        }
        
        result = validator.validate(self.user, plan)
        
        self.assertFalse(result['valid'])
        self.assertTrue(any('computed' in e.lower() for e in result['errors']),
            f"Should reject computed field in fields. Errors: {result['errors']}")
    
    def test_04c_validator_rejects_computed_in_group_by(self):
        """Bug #11: Verify validator rejects computed fields in group_by."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        plan = {
            'steps': [{
                'model': 'product.product',
                'domain': [],
                'group_by': ['qty_available'],  # qty_available is computed
            }]
        }
        
        result = validator.validate(self.user, plan)
        
        self.assertFalse(result['valid'])
        self.assertTrue(any('computed' in e.lower() for e in result['errors']),
            f"Should reject computed field in group_by. Errors: {result['errors']}")
    
    def test_04d_validator_rejects_computed_in_aggregations(self):
        """Bug #11: Verify validator rejects computed fields in aggregations."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        plan = {
            'steps': [{
                'model': 'product.product',
                'domain': [],
                'aggregations': [{'field': 'qty_available', 'op': 'sum'}],  # computed
                'group_by': ['name'],
            }]
        }
        
        result = validator.validate(self.user, plan)
        
        self.assertFalse(result['valid'])
        self.assertTrue(any('computed' in e.lower() for e in result['errors']),
            f"Should reject computed field in aggregations. Errors: {result['errors']}")
    
    def test_04e_validator_accepts_stored_fields(self):
        """Bug #11: Verify validator accepts stored (non-computed) fields."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        plan = {
            'steps': [{
                'model': 'res.users',
                'domain': [('login', '!=', False)],  # login is stored
                'fields': ['name', 'login'],  # both stored
                'group_by': ['login'],  # stored
            }]
        }
        
        result = validator.validate(self.user, plan)
        
        # Should not have computed field errors
        computed_errors = [e for e in result['errors'] if 'computed' in e.lower()]
        self.assertEqual(len(computed_errors), 0,
            f"Should accept stored fields. Errors: {result['errors']}")
    
    def test_04f_is_computed_field_method(self):
        """Bug #11: Test _is_computed_field helper method."""
        validator = self.env['ai.analyst.query.plan.validator']
        
        # Get product.product model
        product_model = self.env['product.product']
        
        # qty_available is computed (not stored)
        is_computed = validator._is_computed_field(product_model, 'qty_available')
        self.assertTrue(is_computed, "qty_available should be identified as computed")
        
        # name is stored
        is_computed = validator._is_computed_field(product_model, 'name')
        self.assertFalse(is_computed, "name should not be identified as computed")

    # =================================================================
    # Test 5: CSV Download URL (JS logic verification via Python tests)
    # =================================================================
    
    def test_05_csv_action_with_download_url(self):
        """Bug #7: Verify actions can contain download_url for CSV downloads."""
        gateway = self.env['ai.analyst.gateway']
        
        # Create a response with download_url (new format)
        response = {
            'answer': 'Test data ready',
            'actions': [{
                'type': 'download_csv',
                'label': 'Download CSV',
                'download_url': '/ai_analyst/boss_export/download?job_token=abc123',
                'enabled': True,
            }]
        }
        
        is_valid, errors = gateway._validate_response_schema(response)
        self.assertTrue(is_valid, f"Response with download_url should be valid: {errors}")
    
    def test_05b_csv_action_legacy_attachment_id(self):
        """Bug #7: Verify actions can still contain attachment_id (legacy format)."""
        gateway = self.env['ai.analyst.gateway']
        
        response = {
            'answer': 'Test data ready',
            'actions': [{
                'type': 'download_csv',
                'label': 'Download CSV',
                'attachment_id': 12345,
                'enabled': True,
            }]
        }
        
        is_valid, errors = gateway._validate_response_schema(response)
        self.assertTrue(is_valid, f"Response with attachment_id should be valid: {errors}")


@tagged('ai_analyst', 'phase1', 'post_install', '-at_install')
class TestPhase1Integration(common.TransactionCase):
    """Integration tests for Phase 1 Quick Wins."""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.user
        cls.company = cls.user.company_id
    
    def test_gateway_end_to_end_schema_validation(self):
        """Test that gateway validates responses in the actual flow."""
        # This is a lightweight test that doesn't actually call the LLM
        # but verifies the schema validation is wired correctly
        
        gateway = self.env['ai.analyst.gateway']
        
        # Test the _ensure_valid_response method directly
        # Simulate a malformed response that an LLM might return
        malformed = {
            'answer': 'Test',
            'invalid_extra_key': 'should not break things',
        }
        
        fixed = gateway._ensure_valid_response(malformed)
        
        # Should be fixed to have answer and meta.validation_errors
        self.assertIn('answer', fixed)
        self.assertIn('meta', fixed)
        self.assertIn('validation_errors', fixed['meta'])
        self.assertIn('original_response_keys', fixed['meta'])
