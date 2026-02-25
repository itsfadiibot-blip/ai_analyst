# -*- coding: utf-8 -*-
"""
Field Relevance Graph - Maps Question Types to Relevant Fields
=============================================================

Determines which fields are relevant for different types of business questions.
Combines Knowledge Base business context with Schema Registry metadata.

Part of Phase 1: Schema-Aware Query Planner Implementation
"""
import json
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class FieldRelevanceGraph(models.Model):
    _name = 'ai.analyst.field.relevance'
    _description = 'AI Analyst Field Relevance Graph'
    _order = 'question_type'
    
    question_type = fields.Char(
        string='Question Type',
        required=True,
        help='Type of business question (e.g., product_catalog, sales_analysis)'
    )
    
    description = fields.Text(
        string='Description',
        help='What this question type covers'
    )
    
    primary_model = fields.Char(
        string='Primary Model',
        required=True,
        help='Main model for this question type (e.g., product.template)'
    )
    
    relevance_json = fields.Text(
        string='Field Relevance (JSON)',
        required=True,
        help='JSON array of field relevance scores'
    )
    
    trigger_keywords = fields.Text(
        string='Trigger Keywords',
        help='Comma-separated keywords that indicate this question type'
    )
    
    priority = fields.Integer(
        string='Priority',
        default=100,
        help='Higher priority = checked first when multiple types match'
    )
    
    active = fields.Boolean(string='Active', default=True)
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    def get_relevant_fields(self, question_text, target_entity=None):
        """Get relevant fields for a question.
        
        Args:
            question_text: User's question
            target_entity: Optional hint (products, orders, etc.)
            
        Returns:
            dict: {
                'question_type': str,
                'primary_model': str,
                'fields': [
                    {'field': str, 'weight': float, 'search_type': str}
                ]
            }
        """
        self.ensure_one()
        
        # Parse relevance JSON
        try:
            fields_list = json.loads(self.relevance_json or '[]')
        except json.JSONDecodeError:
            _logger.error(f"Invalid relevance JSON for {self.question_type}")
            fields_list = []
        
        return {
            'question_type': self.question_type,
            'description': self.description,
            'primary_model': self.primary_model,
            'fields': fields_list
        }
    
    # ========================================================================
    # CLASS METHODS
    # ========================================================================
    
    @api.model
    def find_question_type(self, question_text, target_entity=None):
        """Find the best matching question type for a question.
        
        Args:
            question_text: User's natural language question
            target_entity: Optional entity hint
            
        Returns:
            FieldRelevanceGraph record or None
        """
        question_lower = (question_text or '').lower()
        
        # Get all active question types, ordered by priority
        candidates = self.search([('active', '=', True)], order='priority desc')
        
        matches = []
        
        for candidate in candidates:
            score = candidate._calculate_match_score(question_lower, target_entity)
            if score > 0:
                matches.append((score, candidate))
        
        if not matches:
            return None
        
        # Return highest scoring match
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]
    
    def _calculate_match_score(self, question_lower, target_entity=None):
        """Calculate how well this question type matches the question."""
        score = 0
        
        # Check trigger keywords
        keywords = (self.trigger_keywords or '').split(',')
        keywords = [k.strip().lower() for k in keywords if k.strip()]
        
        for keyword in keywords:
            if keyword in question_lower:
                score += 10  # Base score for keyword match
                
                # Bonus for keyword at start of question
                if question_lower.startswith(keyword):
                    score += 5
        
        # Check target entity match
        if target_entity:
            entity_keywords = {
                'product': ['product', 'item', 'sku', 'catalog'],
                'order': ['order', 'sale', 'purchase', 'transaction'],
                'customer': ['customer', 'partner', 'client'],
                'inventory': ['stock', 'inventory', 'quantity', 'available']
            }
            
            target_lower = target_entity.lower()
            for entity_type, entity_words in entity_keywords.items():
                if target_lower in entity_words or entity_type in target_lower:
                    # This question type's primary model should match entity
                    if any(x in self.primary_model for x in entity_words):
                        score += 20
        
        return score
    
    # ========================================================================
    # SETUP / DATA LOADING
    # ========================================================================
    
    @api.model
    def action_load_default_patterns(self):
        """Load default question type patterns."""
        patterns = [
            {
                'question_type': 'product_catalog',
                'description': 'Product catalog queries - searching products by attributes',
                'primary_model': 'product.template',
                'trigger_keywords': 'product,item,catalog,style,color,season,FW,SS',
                'fields': [
                    {'field': 'name', 'weight': 1.0, 'search_type': 'text'},
                    {'field': 'x_studio_many2many_field_IXz60', 'weight': 0.9, 'search_type': 'season'},
                    {'field': 'x_studio_style_reference', 'weight': 0.8, 'search_type': 'style'},
                    {'field': 'default_code', 'weight': 0.7, 'search_type': 'exact'},
                    {'field': 'list_price', 'weight': 0.6, 'search_type': 'price'},
                    {'field': 'x_studio_color_reference', 'weight': 0.5, 'search_type': 'color_index'},
                    {'field': 'categ_id', 'weight': 0.4, 'search_type': 'category'},
                    {'field': 'active', 'weight': 0.3, 'search_type': 'boolean'}
                ],
                'priority': 100
            },
            {
                'question_type': 'sales_analysis',
                'description': 'Sales analysis - revenue, orders, performance',
                'primary_model': 'sale.order',
                'trigger_keywords': 'sale,order,revenue,turnover,amount,total,buy,purchase',
                'fields': [
                    {'field': 'amount_total', 'weight': 1.0, 'aggregation': 'sum'},
                    {'field': 'date_order', 'weight': 0.9, 'search_type': 'date'},
                    {'field': 'state', 'weight': 0.8, 'filter_values': ['sale', 'done']},
                    {'field': 'partner_id', 'weight': 0.7, 'search_type': 'customer'},
                    {'field': 'origin', 'weight': 0.6, 'search_type': 'channel'},
                    {'field': 'team_id', 'weight': 0.5, 'search_type': 'team'},
                    {'field': 'amount_untaxed', 'weight': 0.4, 'aggregation': 'sum'}
                ],
                'priority': 90
            },
            {
                'question_type': 'inventory_analysis',
                'description': 'Inventory levels, stock on hand, availability',
                'primary_model': 'stock.quant',
                'trigger_keywords': 'stock,inventory,available,quantity,on hand,SOH,warehouse',
                'fields': [
                    {'field': 'quantity', 'weight': 1.0, 'aggregation': 'sum'},
                    {'field': 'product_id', 'weight': 0.9, 'search_type': 'product'},
                    {'field': 'location_id', 'weight': 0.8, 'search_type': 'location'},
                    {'field': 'reserved_quantity', 'weight': 0.7, 'aggregation': 'sum'},
                    {'field': 'available_quantity', 'weight': 0.6, 'aggregation': 'sum'}
                ],
                'priority': 85
            },
            {
                'question_type': 'customer_analysis',
                'description': 'Customer queries, partner information',
                'primary_model': 'res.partner',
                'trigger_keywords': 'customer,client,partner,buyer',
                'fields': [
                    {'field': 'name', 'weight': 1.0, 'search_type': 'text'},
                    {'field': 'email', 'weight': 0.9, 'search_type': 'email'},
                    {'field': 'phone', 'weight': 0.8, 'search_type': 'phone'},
                    {'field': 'city', 'weight': 0.7, 'search_type': 'location'},
                    {'field': 'country_id', 'weight': 0.6, 'search_type': 'country'},
                    {'field': 'customer_rank', 'weight': 0.5, 'search_type': 'rank'}
                ],
                'priority': 80
            },
            {
                'question_type': 'purchase_analysis',
                'description': 'Purchase orders, vendor analysis',
                'primary_model': 'purchase.order',
                'trigger_keywords': 'purchase,PO,vendor,supplier,buying',
                'fields': [
                    {'field': 'amount_total', 'weight': 1.0, 'aggregation': 'sum'},
                    {'field': 'date_approve', 'weight': 0.9, 'search_type': 'date'},
                    {'field': 'partner_id', 'weight': 0.8, 'search_type': 'vendor'},
                    {'field': 'state', 'weight': 0.7, 'filter_values': ['purchase']}
                ],
                'priority': 70
            },
            {
                'question_type': 'accounting_analysis',
                'description': 'Invoices, payments, accounting entries',
                'primary_model': 'account.move',
                'trigger_keywords': 'invoice,bill,payment,accounting,journal',
                'fields': [
                    {'field': 'amount_total', 'weight': 1.0, 'aggregation': 'sum'},
                    {'field': 'date', 'weight': 0.9, 'search_type': 'date'},
                    {'field': 'move_type', 'weight': 0.8, 'search_type': 'type'},
                    {'field': 'state', 'weight': 0.7, 'filter_values': ['posted']},
                    {'field': 'partner_id', 'weight': 0.6, 'search_type': 'partner'}
                ],
                'priority': 60
            }
        ]
        
        created = 0
        for pattern in patterns:
            existing = self.search([('question_type', '=', pattern['question_type'])])
            if existing:
                continue
            
            self.create({
                'question_type': pattern['question_type'],
                'description': pattern['description'],
                'primary_model': pattern['primary_model'],
                'trigger_keywords': pattern['trigger_keywords'],
                'relevance_json': json.dumps(pattern['fields']),
                'priority': pattern['priority']
            })
            created += 1
        
        _logger.info(f"Loaded {created} default field relevance patterns")
        return created
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_field_weights(self):
        """Get fields as a weighted dict for ranking."""
        try:
            fields_list = json.loads(self.relevance_json or '[]')
        except:
            return {}
        
        return {f['field']: f.get('weight', 0.5) for f in fields_list}
