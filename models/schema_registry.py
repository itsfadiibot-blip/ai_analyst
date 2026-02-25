# -*- coding: utf-8 -*-
"""
Schema Registry - Odoo Metadata Loader
======================================
Loads and caches Odoo schema metadata (models, fields, relations)
for use by the Schema-Aware Query Planner.

Part of Phase 1: Schema-Aware Query Planner Implementation
"""
import json
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SchemaRegistry(models.Model):
    _name = 'ai.analyst.schema.registry'
    _description = 'AI Analyst Schema Registry'
    
    name = fields.Char(string='Registry Name', required=True, default='default')
    last_refresh = fields.Datetime(string='Last Refresh')
    schema_cache = fields.Text(string='Schema Cache (JSON)', help='Cached schema metadata')
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    def get_model_schema(self, model_name):
        """Get schema for a specific model.
        
        Returns:
            dict: Model schema with fields and relations
        """
        self.ensure_one()
        schema = self._load_schema()
        return schema.get('models', {}).get(model_name, {})
    
    def get_field_info(self, model_name, field_name):
        """Get information about a specific field.
        
        Returns:
            dict: Field metadata (type, relation, required, etc.)
        """
        model_schema = self.get_model_schema(model_name)
        return model_schema.get('fields', {}).get(field_name, {})
    
    def get_related_model(self, model_name, field_name):
        """Get the related model for a relation field.
        
        Returns:
            str: Related model name or None
        """
        field_info = self.get_field_info(model_name, field_name)
        return field_info.get('relation')
    
    def get_model_list(self):
        """Get list of all available models.
        
        Returns:
            list: Model names
        """
        schema = self._load_schema()
        return list(schema.get('models', {}).keys())
    
    def search_fields(self, keyword):
        """Search for fields containing keyword in name or description.
        
        Returns:
            list: Matching fields with model info
        """
        schema = self._load_schema()
        results = []
        
        for model_name, model_data in schema.get('models', {}).items():
            for field_name, field_data in model_data.get('fields', {}).items():
                if keyword.lower() in field_name.lower():
                    results.append({
                        'model': model_name,
                        'field': field_name,
                        'type': field_data.get('type'),
                        'relation': field_data.get('relation')
                    })
        
        return results
    
    # ========================================================================
    # SCHEMA BUILDING
    # ========================================================================
    
    def action_refresh_schema(self):
        """Refresh schema from Odoo metadata."""
        self.ensure_one()
        
        schema = {
            'models': {},
            'relations': {},
            'generated_at': fields.Datetime.now().isoformat()
        }
        
        # Get all models
        model_objs = self.env['ir.model'].sudo().search([])
        
        for model in model_objs:
            model_schema = self._build_model_schema(model)
            if model_schema:
                schema['models'][model.model] = model_schema
        
        # Build relation index
        schema['relations'] = self._build_relation_index(schema['models'])
        
        # Cache it
        self.schema_cache = json.dumps(schema, indent=2)
        self.last_refresh = fields.Datetime.now()
        
        _logger.info(f"Schema refreshed: {len(schema['models'])} models")
        return True
    
    def _build_model_schema(self, model):
        """Build schema for a single model."""
        schema = {
            'name': model.name,
            'description': '',  # Could load from docstring
            'fields': {},
            'inherits': []
        }
        
        # Get all fields for this model
        field_objs = self.env['ir.model.fields'].sudo().search([
            ('model_id', '=', model.id),
            ('store', '=', True)  # Only stored fields
        ])
        
        for field in field_objs:
            field_info = {
                'type': field.ttype,
                'required': field.required,
                'readonly': field.readonly,
                'string': field.field_description,
                'help': field.help or '',
            }
            
            # Add relation info
            if field.ttype in ('many2one', 'one2many', 'many2many'):
                field_info['relation'] = field.relation
                if field.ttype == 'many2one':
                    field_info['ondelete'] = field.on_delete
            
            # Add selection values
            if field.ttype == 'selection' and field.selection:
                try:
                    # Parse selection string "[('key', 'value'), ...]"
                    import ast
                    selection = ast.literal_eval(field.selection)
                    field_info['selection'] = {k: v for k, v in selection}
                except:
                    pass
            
            schema['fields'][field.name] = field_info
        
        return schema
    
    def _build_relation_index(self, models_schema):
        """Build index of model relationships."""
        index = {}
        
        for model_name, model_data in models_schema.items():
            index[model_name] = {
                'depends_on': [],  # Models this model refers to
                'depended_by': []  # Models that refer to this model
            }
            
            for field_name, field_data in model_data.get('fields', {}).items():
                if field_data.get('relation'):
                    related_model = field_data['relation']
                    
                    # This model depends on related model
                    if field_data['type'] == 'many2one':
                        index[model_name]['depends_on'].append({
                            'model': related_model,
                            'field': field_name,
                            'type': 'many2one'
                        })
                    
                    # Track reverse relation
                    if related_model not in index:
                        index[related_model] = {'depends_on': [], 'depended_by': []}
                    
                    index[related_model]['depended_by'].append({
                        'model': model_name,
                        'field': field_name,
                        'type': field_data['type']
                    })
        
        return index
    
    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================
    
    def _load_schema(self):
        """Load schema from cache or build if empty."""
        if not self.schema_cache:
            self.action_refresh_schema()
        
        try:
            return json.loads(self.schema_cache or '{}')
        except json.JSONDecodeError:
            _logger.error("Invalid schema cache, rebuilding...")
            self.action_refresh_schema()
            return json.loads(self.schema_cache or '{}')
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_join_path(self, from_model, to_model):
        """Find the shortest join path between two models.
        
        Returns:
            list: Sequence of fields to join through
        """
        schema = self._load_schema()
        relations = schema.get('relations', {})
        
        # Simple BFS to find path
        from collections import deque
        
        queue = deque([(from_model, [])])
        visited = {from_model}
        
        while queue:
            current, path = queue.popleft()
            
            if current == to_model:
                return path
            
            current_relations = relations.get(current, {})
            
            # Follow depends_on relations
            for rel in current_relations.get('depends_on', []):
                next_model = rel['model']
                if next_model not in visited:
                    visited.add(next_model)
                    new_path = path + [{'field': rel['field'], 'to_model': next_model}]
                    queue.append((next_model, new_path))
            
            # Follow depended_by relations
            for rel in current_relations.get('depended_by', []):
                next_model = rel['model']
                if next_model not in visited:
                    visited.add(next_model)
                    # Reverse relation - need to find inverse field
                    new_path = path + [{'field': f"{rel['field']}", 'to_model': next_model, 'reverse': True}]
                    queue.append((next_model, new_path))
        
        return None  # No path found
    
    def get_field_chain(self, model_name, field_path):
        """Resolve a dot-separated field path.
        
        Example: 'partner_id.country_id.name' → resolves chain of relations
        
        Returns:
            list: Resolved field chain with model info
        """
        parts = field_path.split('.')
        chain = []
        current_model = model_name
        
        for part in parts:
            field_info = self.get_field_info(current_model, part)
            if not field_info:
                return None  # Invalid path
            
            chain.append({
                'model': current_model,
                'field': part,
                'type': field_info['type'],
                'relation': field_info.get('relation')
            })
            
            # Move to related model for next part
            if field_info.get('relation'):
                current_model = field_info['relation']
        
        return chain
