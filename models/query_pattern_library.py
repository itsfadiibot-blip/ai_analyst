# -*- coding: utf-8 -*-
"""
Query Pattern Library - Pre-built Query Templates
=================================================

Pre-defined query structures for common business questions.
Works with Schema Registry and Field Relevance Graph.

Part of Phase 2: Schema-Aware Query Planner Implementation
"""
import json
import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class QueryPatternLibrary(models.Model):
    _name = 'ai.analyst.query.pattern'
    _description = 'AI Analyst Query Pattern Library'
    _order = 'priority desc, name'
    
    name = fields.Char(string='Pattern Name', required=True)
    description = fields.Text(string='Description')
    
    # Pattern matching
    trigger_keywords = fields.Text(
        string='Trigger Keywords',
        help='Comma-separated keywords that trigger this pattern'
    )
    
    trigger_regex = fields.Char(
        string='Trigger Regex',
        help='Optional regex pattern for matching'
    )
    
    # Query structure
    primary_model = fields.Char(string='Primary Model', required=True)
    
    query_structure_json = fields.Text(
        string='Query Structure (JSON)',
        required=True,
        help='JSON definition of the query structure'
    )
    
    # Configuration
    requires_date_filter = fields.Boolean(
        string='Requires Date Filter',
        default=False,
        help='If True, pattern needs date range'
    )
    
    requires_aggregation = fields.Boolean(
        string='Requires Aggregation',
        default=False
    )
    
    default_aggregation = fields.Selection([
        ('count', 'Count'),
        ('sum', 'Sum'),
        ('avg', 'Average'),
        ('min', 'Minimum'),
        ('max', 'Maximum')
    ], string='Default Aggregation')
    
    default_group_by = fields.Char(
        string='Default Group By',
        help='Field to group results by'
    )
    
    priority = fields.Integer(string='Priority', default=100)
    active = fields.Boolean(string='Active', default=True)
    
    # ========================================================================
    # PATTERN MATCHING
    # ========================================================================
    
    def matches_question(self, question_text, extracted_entities=None):
        """Check if this pattern matches the question.
        
        Returns:
            dict: Match details including confidence score, or None
        """
        self.ensure_one()
        question_lower = (question_text or '').lower()
        
        score = 0
        matched_keywords = []
        
        # Check trigger keywords
        keywords = [k.strip().lower() for k in (self.trigger_keywords or '').split(',') if k.strip()]
        for keyword in keywords:
            if keyword in question_lower:
                score += 10
                matched_keywords.append(keyword)
        
        # Check regex pattern
        if self.trigger_regex:
            try:
                if re.search(self.trigger_regex, question_text, re.IGNORECASE):
                    score += 20
            except re.error:
                _logger.warning(f"Invalid regex in pattern {self.name}: {self.trigger_regex}")
        
        # Check entity compatibility
        if extracted_entities:
            entity_type = extracted_entities.get('target')
            if entity_type:
                entity_model_map = {
                    'product': 'product.template',
                    'order': 'sale.order',
                    'customer': 'res.partner',
                    'inventory': 'stock.quant'
                }
                expected_model = entity_model_map.get(entity_type)
                if expected_model and expected_model == self.primary_model:
                    score += 15
        
        if score == 0:
            return None
        
        return {
            'pattern': self,
            'score': score,
            'matched_keywords': matched_keywords
        }
    
    # ========================================================================
    # QUERY BUILDING
    # ========================================================================
    
    def build_query_plan(self, user_question, extracted_entities=None, context=None):
        """Build a query plan using this pattern.
        
        Returns:
            dict: Query plan ready for execution
        """
        self.ensure_one()
        
        try:
            structure = json.loads(self.query_structure_json or '{}')
        except json.JSONDecodeError:
            _logger.error(f"Invalid query structure JSON in pattern {self.name}")
            return None
        
        # Start with base structure
        plan = {
            'pattern_used': self.name,
            'steps': []
        }
        
        # Get the primary query step
        base_step = structure.get('base_query', {})
        
        # Build domain filters
        domain = list(base_step.get('domain', []))
        
        # Add entity-specific filters
        if extracted_entities:
            entity_domain = self._build_entity_domain(extracted_entities)
            domain.extend(entity_domain)
        
        # Build the step
        step = {
            'id': f"{self.name}_main",
            'model': self.primary_model,
            'method': base_step.get('method', 'search_read'),
            'domain': domain,
            'fields': base_step.get('fields', ['name']),
            'limit': base_step.get('limit', 100)
        }
        
        # Add aggregation if needed
        if self.requires_aggregation or extracted_entities.get('operation') in ('sum', 'count', 'avg'):
            step['aggregation'] = self._build_aggregation(extracted_entities)
        
        # Add group_by if specified
        if self.default_group_by:
            step['group_by'] = self.default_group_by
        
        plan['steps'].append(step)
        
        # Add join steps if specified
        join_steps = structure.get('joins', [])
        for join_def in join_steps:
            join_step = self._build_join_step(join_def, extracted_entities)
            if join_step:
                plan['steps'].append(join_step)
        
        return plan
    
    def _build_entity_domain(self, entities):
        """Build domain filters from extracted entities."""
        domain = []
        
        # Date filtering
        if entities.get('date_range'):
            date_range = entities['date_range']
            # Find date field for this model
            date_field = self._get_date_field()
            if date_field:
                domain.append([date_field, '>=', date_range.get('start')])
                domain.append([date_field, '<=', date_range.get('end')])
        
        # Season filtering (product pattern)
        if entities.get('season') and self.primary_model == 'product.template':
            season_code = entities['season']
            # Use ilike for partial match
            domain.append(['x_studio_many2many_field_IXz60.name', 'ilike', f"%{season_code}%"])
        
        # Color filtering
        if entities.get('color') and self.primary_model == 'product.template':
            color = entities['color']
            # Search by product name containing color
            domain.append(['name', 'ilike', f"%{color}%"])
        
        # Status/state filtering
        if entities.get('status'):
            status = entities['status']
            state_mapping = self._get_state_mapping()
            db_value = state_mapping.get(status.lower(), status)
            domain.append(['state', '=', db_value])
        
        # Active filter (default to active records)
        if self.primary_model in ['product.template', 'product.product', 'res.partner']:
            domain.append(['active', '=', True])
        
        return domain
    
    def _build_aggregation(self, entities):
        """Build aggregation specification."""
        operation = entities.get('operation', self.default_aggregation or 'count')
        
        # Determine field to aggregate
        field_map = {
            'sale.order': 'amount_total',
            'purchase.order': 'amount_total',
            'account.move': 'amount_total',
            'stock.quant': 'quantity',
            'sale.order.line': 'price_subtotal',
            'product.template': 'id'  # Count
        }
        
        agg_field = field_map.get(self.primary_model, 'id')
        
        return {
            'operation': operation,
            'field': agg_field,
            'group_by': entities.get('group_by') or self.default_group_by
        }
    
    def _build_join_step(self, join_def, entities):
        """Build a join step for related models."""
        return {
            'id': join_def.get('id', 'join_step'),
            'model': join_def['model'],
            'relation_field': join_def['relation_field'],
            'domain': join_def.get('domain', []),
            'fields': join_def.get('fields', ['name'])
        }
    
    def _get_date_field(self):
        """Get the date field for this model."""
        date_fields = {
            'sale.order': 'date_order',
            'purchase.order': 'date_approve',
            'account.move': 'date',
            'pos.order': 'date_order',
            'stock.move': 'date'
        }
        return date_fields.get(self.primary_model)
    
    def _get_state_mapping(self):
        """Get state value mapping for this model."""
        mappings = {
            'sale.order': {
                'confirmed': 'sale',
                'done': 'done',
                'draft': 'draft',
                'cancelled': 'cancel',
                'sent': 'sent'
            },
            'purchase.order': {
                'confirmed': 'purchase',
                'done': 'done',
                'draft': 'draft',
                'cancelled': 'cancel'
            },
            'account.move': {
                'posted': 'posted',
                'draft': 'draft',
                'cancelled': 'cancel'
            }
        }
        return mappings.get(self.primary_model, {})
    
    # ========================================================================
    # SETUP / DEFAULT PATTERNS
    # ========================================================================
    
    @api.model
    def action_load_default_patterns(self):
        """Load default query patterns."""
        patterns = [
            {
                'name': 'product_by_season',
                'description': 'Find products by season code (FW25, SS26, etc.)',
                'trigger_keywords': 'season,FW,SS,spring,summer,fall,winter,collection',
                'primary_model': 'product.template',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['active', '=', True]],
                        'fields': ['name', 'default_code', 'list_price', 'x_studio_style_reference'],
                        'limit': 100
                    }
                },
                'requires_date_filter': False,
                'priority': 100
            },
            {
                'name': 'product_by_color',
                'description': 'Find products by color (searches name and attributes)',
                'trigger_keywords': 'color,red,blue,black,white,green,yellow,pink',
                'primary_model': 'product.template',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['active', '=', True]],
                        'fields': ['name', 'default_code', 'list_price'],
                        'limit': 100
                    }
                },
                'priority': 95
            },
            {
                'name': 'product_by_style',
                'description': 'Find products by style reference code',
                'trigger_keywords': 'style,JC,reference,code,MAY,MYRL',
                'trigger_regex': r'\b(JC|MAY|MYRL)\d+\b',
                'primary_model': 'product.template',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['active', '=', True]],
                        'fields': ['name', 'default_code', 'list_price', 'x_studio_style_reference'],
                        'limit': 50
                    }
                },
                'priority': 90
            },
            {
                'name': 'sales_by_period',
                'description': 'Sales totals grouped by time period',
                'trigger_keywords': 'sales,revenue,turnover,total orders,how much did we sell',
                'primary_model': 'sale.order',
                'query_structure': {
                    'base_query': {
                        'method': 'read_group',
                        'domain': [['state', 'in', ['sale', 'done']]],
                        'fields': ['amount_total:sum', 'date_order'],
                        'group_by': ['date_order:month'],
                        'limit': 100
                    }
                },
                'requires_date_filter': True,
                'requires_aggregation': True,
                'default_aggregation': 'sum',
                'priority': 100
            },
            {
                'name': 'sales_count',
                'description': 'Count of orders or order lines',
                'trigger_keywords': 'how many orders,order count,number of sales,how many products sold',
                'primary_model': 'sale.order',
                'query_structure': {
                    'base_query': {
                        'method': 'search_count',
                        'domain': [['state', 'in', ['sale', 'done']]],
                        'limit': 1
                    }
                },
                'requires_aggregation': True,
                'default_aggregation': 'count',
                'priority': 95
            },
            {
                'name': 'inventory_levels',
                'description': 'Current stock on hand by product',
                'trigger_keywords': 'stock,inventory,on hand,available,quantity,SOH,how many in stock',
                'primary_model': 'stock.quant',
                'query_structure': {
                    'base_query': {
                        'method': 'read_group',
                        'domain': [['location_id.usage', '=', 'internal']],
                        'fields': ['quantity:sum', 'product_id'],
                        'group_by': ['product_id'],
                        'limit': 100
                    }
                },
                'requires_aggregation': True,
                'default_aggregation': 'sum',
                'default_group_by': 'product_id',
                'priority': 100
            },
            {
                'name': 'customer_list',
                'description': 'List or search customers',
                'trigger_keywords': 'customer,client,partner,buyer',
                'primary_model': 'res.partner',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['customer_rank', '>', 0]],
                        'fields': ['name', 'email', 'phone', 'city', 'country_id'],
                        'limit': 50
                    }
                },
                'priority': 90
            },
            {
                'name': 'purchase_orders',
                'description': 'Purchase order analysis',
                'trigger_keywords': 'purchase,PO,vendor,supplier,buying',
                'primary_model': 'purchase.order',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['state', 'in', ['purchase', 'done']]],
                        'fields': ['name', 'partner_id', 'amount_total', 'date_approve'],
                        'limit': 50
                    }
                },
                'requires_date_filter': True,
                'priority': 80
            },
            {
                'name': 'accounting_moves',
                'description': 'Journal entries and invoices',
                'trigger_keywords': 'invoice,bill,journal entry,accounting,posted',
                'primary_model': 'account.move',
                'query_structure': {
                    'base_query': {
                        'method': 'search_read',
                        'domain': [['state', '=', 'posted']],
                        'fields': ['name', 'partner_id', 'amount_total', 'date', 'move_type'],
                        'limit': 50
                    }
                },
                'requires_date_filter': True,
                'priority': 70
            },
            {
                'name': 'product_count',
                'description': 'Count of products in catalog',
                'trigger_keywords': 'how many products,product count,total products,catalog size',
                'primary_model': 'product.template',
                'query_structure': {
                    'base_query': {
                        'method': 'search_count',
                        'domain': [['active', '=', True]],
                        'limit': 1
                    }
                },
                'requires_aggregation': True,
                'default_aggregation': 'count',
                'priority': 100
            }
        ]
        
        created = 0
        for pattern_data in patterns:
            existing = self.search([('name', '=', pattern_data['name'])])
            if existing:
                continue
            
            self.create({
                'name': pattern_data['name'],
                'description': pattern_data['description'],
                'trigger_keywords': pattern_data.get('trigger_keywords', ''),
                'trigger_regex': pattern_data.get('trigger_regex', ''),
                'primary_model': pattern_data['primary_model'],
                'query_structure_json': json.dumps(pattern_data['query_structure']),
                'requires_date_filter': pattern_data.get('requires_date_filter', False),
                'requires_aggregation': pattern_data.get('requires_aggregation', False),
                'default_aggregation': pattern_data.get('default_aggregation'),
                'default_group_by': pattern_data.get('default_group_by'),
                'priority': pattern_data.get('priority', 100)
            })
            created += 1
        
        _logger.info(f"Loaded {created} default query patterns")
        return created
    
    # ========================================================================
    # CLASS METHODS
    # ========================================================================
    
    @api.model
    def find_best_pattern(self, question_text, extracted_entities=None):
        """Find the best matching pattern for a question.
        
        Returns:
            QueryPatternLibrary record or None
        """
        patterns = self.search([('active', '=', True)])
        
        matches = []
        for pattern in patterns:
            match = pattern.matches_question(question_text, extracted_entities)
            if match:
                matches.append(match)
        
        if not matches:
            return None
        
        # Sort by score
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches[0]['pattern']
