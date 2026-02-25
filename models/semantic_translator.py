# -*- coding: utf-8 -*-
"""
Semantic Translator - User Language to Database Values
======================================================

Converts natural language user input to database-compatible values.
Handles synonyms, patterns, and business-specific terminology.

Part of Phase 2: Schema-Aware Query Planner Implementation
"""
import json
import logging
import re
from datetime import datetime, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class SemanticTranslator(models.Model):
    _name = 'ai.analyst.semantic.translator'
    _description = 'AI Analyst Semantic Translator'
    
    name = fields.Char(string='Name', required=True)
    category = fields.Selection([
        ('season', 'Season Codes'),
        ('color', 'Color Names'),
        ('status', 'Status/State'),
        ('channel', 'Sales Channel'),
        ('time', 'Time Periods'),
        ('generic', 'Generic Synonyms')
    ], string='Category', required=True)
    
    # Translation rules
    rules_json = fields.Text(
        string='Translation Rules (JSON)',
        required=True,
        help='JSON array of translation rules'
    )
    
    priority = fields.Integer(string='Priority', default=100)
    active = fields.Boolean(string='Active', default=True)
    
    # ========================================================================
    # TRANSLATION API
    # ========================================================================
    
    def translate(self, user_value, context=None):
        """Translate a user value to database value.
        
        Args:
            user_value: String from user's question
            context: Optional context (e.g., {'field': 'season', 'model': 'product.template'})
            
        Returns:
            dict: {
                'success': bool,
                'original': str,
                'translated': str,
                'operator': str (e.g., '=', 'ilike', 'in'),
                'explanation': str
            }
        """
        self.ensure_one()
        
        try:
            rules = json.loads(self.rules_json or '[]')
        except json.JSONDecodeError:
            return {
                'success': False,
                'original': user_value,
                'error': 'Invalid rules JSON'
            }
        
        user_lower = (user_value or '').lower().strip()
        
        for rule in rules:
            match_type = rule.get('match_type', 'exact')
            
            if match_type == 'exact':
                if user_lower == rule['pattern'].lower():
                    return self._build_result(user_value, rule)
                    
            elif match_type == 'contains':
                if rule['pattern'].lower() in user_lower:
                    return self._build_result(user_value, rule)
                    
            elif match_type == 'regex':
                try:
                    if re.search(rule['pattern'], user_value, re.IGNORECASE):
                        return self._build_result(user_value, rule, match_group=user_value)
                except re.error:
                    continue
                    
            elif match_type == 'startswith':
                if user_lower.startswith(rule['pattern'].lower()):
                    return self._build_result(user_value, rule)
        
        # No match found
        return {
            'success': False,
            'original': user_value,
            'translated': user_value,
            'operator': '=',
            'explanation': f'No translation found for "{user_value}"'
        }
    
    def _build_result(self, original, rule, match_group=None):
        """Build translation result from rule."""
        result = {
            'success': True,
            'original': original,
            'translated': rule.get('translation', original),
            'operator': rule.get('operator', '='),
            'explanation': rule.get('explanation', '')
        }
        
        # Apply transformation if specified
        transform = rule.get('transform')
        if transform:
            if transform == 'uppercase':
                result['translated'] = result['translated'].upper()
            elif transform == 'lowercase':
                result['translated'] = result['translated'].lower()
            elif transform == 'wildcard_prefix':
                result['translated'] = f"%{result['translated']}"
            elif transform == 'wildcard_suffix':
                result['translated'] = f"{result['translated']}%"
            elif transform == 'wildcard_both':
                result['translated'] = f"%{result['translated']}%"
        
        return result
    
    # ========================================================================
    # CLASS METHODS
    # ========================================================================
    
    @api.model
    def translate_value(self, user_value, category=None, context=None):
        """Translate a value using appropriate translator.
        
        Args:
            user_value: User's input value
            category: Optional category hint ('season', 'color', etc.)
            context: Additional context
            
        Returns:
            dict: Translation result
        """
        domain = [('active', '=', True)]
        if category:
            domain.append(('category', '=', category))
        
        translators = self.search(domain, order='priority desc')
        
        for translator in translators:
            result = translator.translate(user_value, context)
            if result.get('success'):
                return result
        
        # No translator found, return as-is
        return {
            'success': True,
            'original': user_value,
            'translated': user_value,
            'operator': '=',
            'explanation': 'No translation needed'
        }
    
    @api.model
    def parse_date_range(self, time_expression):
        """Parse time expressions like 'last month', 'this week', 'Q1 2024'.
        
        Returns:
            dict: {'start': date_string, 'end': date_string} or None
        """
        today = datetime.now()
        time_lower = (time_expression or '').lower().strip()
        
        # Last/This/Next period patterns
        patterns = [
            (r'last month', lambda: (
                (today.replace(day=1) - timedelta(days=1)).replace(day=1),
                today.replace(day=1) - timedelta(days=1)
            )),
            (r'this month', lambda: (
                today.replace(day=1),
                (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            )),
            (r'last week', lambda: (
                today - timedelta(days=today.weekday() + 7),
                today - timedelta(days=today.weekday() + 1)
            )),
            (r'this week', lambda: (
                today - timedelta(days=today.weekday()),
                today + timedelta(days=6 - today.weekday())
            )),
            (r'yesterday', lambda: (
                today - timedelta(days=1),
                today - timedelta(days=1)
            )),
            (r'today', lambda: (
                today,
                today
            )),
            (r'last year', lambda: (
                today.replace(year=today.year - 1, month=1, day=1),
                today.replace(year=today.year - 1, month=12, day=31)
            )),
            (r'this year', lambda: (
                today.replace(month=1, day=1),
                today.replace(month=12, day=31)
            )),
        ]
        
        for pattern, date_func in patterns:
            if re.search(pattern, time_lower):
                start, end = date_func()
                return {
                    'start': start.strftime('%Y-%m-%d'),
                    'end': end.strftime('%Y-%m-%d'),
                    'expression': time_expression
                }
        
        # Try to parse specific date formats
        try:
            # January 2024, Jan 2024
            month_year = re.match(r'(\w+)\s+(\d{4})', time_expression)
            if month_year:
                month_name, year = month_year.groups()
                month_num = datetime.strptime(month_name[:3], '%b').month
                start = datetime(int(year), month_num, 1)
                if month_num == 12:
                    end = datetime(int(year), 12, 31)
                else:
                    end = datetime(int(year), month_num + 1, 1) - timedelta(days=1)
                return {
                    'start': start.strftime('%Y-%m-%d'),
                    'end': end.strftime('%Y-%m-%d'),
                    'expression': time_expression
                }
        except:
            pass
        
        return None
    
    # ========================================================================
    # SETUP / DEFAULT TRANSLATORS
    # ========================================================================
    
    @api.model
    def action_load_default_translators(self):
        """Load default semantic translators."""
        
        translators = [
            {
                'name': 'Season Codes',
                'category': 'season',
                'rules': [
                    {
                        'pattern': 'FW25',
                        'match_type': 'contains',
                        'translation': 'FW25',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Fall/Winter 2025 season (any age group)'
                    },
                    {
                        'pattern': 'SS25',
                        'match_type': 'contains',
                        'translation': 'SS25',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Spring/Summer 2025 season (any age group)'
                    },
                    {
                        'pattern': 'FW26',
                        'match_type': 'contains',
                        'translation': 'FW26',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Fall/Winter 2026 season'
                    },
                    {
                        'pattern': 'SS26',
                        'match_type': 'contains',
                        'translation': 'SS26',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Spring/Summer 2026 season'
                    },
                    {
                        'pattern': 'fall winter',
                        'match_type': 'contains',
                        'translation': 'FW',
                        'operator': 'ilike',
                        'transform': 'wildcard_suffix',
                        'explanation': 'Fall/Winter season (any year)'
                    },
                    {
                        'pattern': 'spring summer',
                        'match_type': 'contains',
                        'translation': 'SS',
                        'operator': 'ilike',
                        'transform': 'wildcard_suffix',
                        'explanation': 'Spring/Summer season (any year)'
                    },
                    {
                        'pattern': r'(\d{2})FW(\d{2})',
                        'match_type': 'regex',
                        'translation': '{match}',
                        'operator': '=',
                        'explanation': 'Full season code (age+season+year)'
                    }
                ],
                'priority': 100
            },
            {
                'name': 'Order Status',
                'category': 'status',
                'rules': [
                    {
                        'pattern': 'confirmed',
                        'match_type': 'exact',
                        'translation': 'sale',
                        'operator': '=',
                        'explanation': 'Confirmed order state'
                    },
                    {
                        'pattern': 'done',
                        'match_type': 'exact',
                        'translation': 'done',
                        'operator': '=',
                        'explanation': 'Completed order state'
                    },
                    {
                        'pattern': 'draft',
                        'match_type': 'exact',
                        'translation': 'draft',
                        'operator': '=',
                        'explanation': 'Draft order state'
                    },
                    {
                        'pattern': 'cancelled',
                        'match_type': 'exact',
                        'translation': 'cancel',
                        'operator': '=',
                        'explanation': 'Cancelled order state'
                    },
                    {
                        'pattern': 'sent',
                        'match_type': 'exact',
                        'translation': 'sent',
                        'operator': '=',
                        'explanation': 'Sent quotation state'
                    },
                    {
                        'pattern': 'posted',
                        'match_type': 'exact',
                        'translation': 'posted',
                        'operator': '=',
                        'explanation': 'Posted accounting entry'
                    },
                    {
                        'pattern': 'active',
                        'match_type': 'exact',
                        'translation': 'true',
                        'operator': '=',
                        'explanation': 'Active record'
                    }
                ],
                'priority': 90
            },
            {
                'name': 'Sales Channels',
                'category': 'channel',
                'rules': [
                    {
                        'pattern': 'online',
                        'match_type': 'exact',
                        'translation': 'SFCC',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Online orders (Salesforce Commerce Cloud)'
                    },
                    {
                        'pattern': 'website',
                        'match_type': 'exact',
                        'translation': 'SFCC',
                        'operator': 'ilike',
                        'transform': 'wildcard_both',
                        'explanation': 'Website orders'
                    },
                    {
                        'pattern': 'pos',
                        'match_type': 'exact',
                        'translation': 'pos',
                        'operator': '=',
                        'explanation': 'Point of Sale (in-store)'
                    },
                    {
                        'pattern': 'store',
                        'match_type': 'exact',
                        'translation': 'pos',
                        'operator': '=',
                        'explanation': 'Store orders'
                    },
                    {
                        'pattern': 'farfetch',
                        'match_type': 'exact',
                        'translation': 'Farfetch',
                        'operator': 'ilike',
                        'explanation': 'Farfetch marketplace orders'
                    }
                ],
                'priority': 80
            },
            {
                'name': 'Generic Synonyms',
                'category': 'generic',
                'rules': [
                    {
                        'pattern': 'customer',
                        'match_type': 'exact',
                        'translation': 'customer',
                        'explanation': 'Customer/B2C context'
                    },
                    {
                        'pattern': 'client',
                        'match_type': 'exact',
                        'translation': 'customer',
                        'explanation': 'Client = Customer'
                    },
                    {
                        'pattern': 'vendor',
                        'match_type': 'exact',
                        'translation': 'supplier',
                        'explanation': 'Vendor = Supplier'
                    },
                    {
                        'pattern': 'sku',
                        'match_type': 'exact',
                        'translation': 'default_code',
                        'explanation': 'SKU = Internal Reference'
                    }
                ],
                'priority': 50
            }
        ]
        
        created = 0
        for trans_data in translators:
            existing = self.search([('name', '=', trans_data['name'])])
            if existing:
                continue
            
            self.create({
                'name': trans_data['name'],
                'category': trans_data['category'],
                'rules_json': json.dumps(trans_data['rules']),
                'priority': trans_data['priority']
            })
            created += 1
        
        _logger.info(f"Loaded {created} default semantic translators")
        return created
