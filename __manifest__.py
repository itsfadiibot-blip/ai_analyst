# -*- coding: utf-8 -*-
{
    'name': 'AI Analyst',
    'version': '17.0.4.0.0',
    'category': 'Productivity',
    'summary': 'AI-powered business analytics with natural language chat interface',
    'description': """
AI Analyst Ã¢â‚¬â€ Chat-First Business Intelligence for Odoo
=======================================================

Ask business questions in natural language. Get answers with KPI cards,
tables, charts, and downloadable CSV exports Ã¢â‚¬â€ without leaving Odoo.

Features:
- Natural language queries against your Odoo data
- KPI cards, data tables, and Chart.js visualizations
- CSV export for any result
- Saved reports and dashboard pinning
- Full audit trail of every query and tool call
- Multi-company and access-control aware
- Provider-agnostic AI backend (Claude, OpenAI, Azure, etc.)
- READ-ONLY by design Ã¢â‚¬â€ no write access to your data

Security:
- Allowlisted tools only Ã¢â‚¬â€ AI cannot run arbitrary queries
- All queries run with the user's own permissions (with_user)
- No sudo() bypass Ã¢â‚¬â€ ever
- Row limits, query timeouts, tool-call budgets
- Prompt injection defenses
- Complete audit logging
    """,
    'author': 'AI Analyst Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'sale',
        'point_of_sale',
        'account',
        'stock',
        'purchase',
        'contacts',
    ],
    'data': [
        # Security
        'security/ai_analyst_groups.xml',
        'security/ir.model.access.csv',
        'security/ai_analyst_rules.xml',
        'security/workspace_rules.xml',
        'security/dimension_rules.xml',
        'security/field_kb_rules.xml',
        # Data
        'data/ai_analyst_config_data.xml',
        'data/ai_analyst_cron.xml',
        'data/workspace_data.xml',
        'data/dimension_data.xml',
        'data/season_data.xml',
        # Views (actions first, menus last)
        'views/ai_analyst_conversation_views.xml',
        'views/ai_analyst_provider_config_views.xml',
        'views/ai_analyst_audit_views.xml',
        'views/ai_analyst_saved_report_views.xml',
        'views/dashboard_views.xml',
        'views/workspace_views.xml',
        'views/dimension_views.xml',
        'views/field_kb_views.xml',
        'views/ai_analyst_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'assets': {
        'web.assets_backend': [
            'ai_analyst/static/src/scss/ai_analyst.scss',
            'ai_analyst/static/src/scss/ai_dashboard.scss',
            'ai_analyst/static/src/js/workspace_selector.js',
            'ai_analyst/static/src/xml/workspace_selector.xml',
            'ai_analyst/static/src/components/ai_analyst_action.js',
            'ai_analyst/static/src/components/ai_analyst_action.xml',
            'ai_analyst/static/src/js/dashboard_client_action.js',
            'ai_analyst/static/src/js/components/dashboard_grid.js',
            'ai_analyst/static/src/xml/dashboard_templates.xml',
            'ai_analyst/static/lib/chart.min.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

