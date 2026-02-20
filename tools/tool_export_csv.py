# -*- coding: utf-8 -*-
"""Tool: export_csv — Export the last query result as a downloadable CSV file."""
import base64
import csv
import io
import json
import logging
from datetime import datetime

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class ExportCSVTool(BaseTool):
    name = 'export_csv'
    description = (
        'Export data from a previous tool call result as a downloadable CSV file. '
        'Creates an attachment that the user can download. '
        'Use this when the user asks to export or download results.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'data_ref': {
                'type': 'string',
                'description': (
                    'Reference to previous tool result to export. '
                    'Use "last_result" to export the most recent data.'
                ),
                'default': 'last_result',
            },
            'filename': {
                'type': 'string',
                'description': 'Desired filename (without extension)',
                'default': 'ai_analyst_export',
            },
        },
        'required': [],
    }

    def execute(self, env, user, params):
        filename = params.get('filename', 'ai_analyst_export')
        # Sanitize filename
        filename = ''.join(
            c for c in filename if c.isalnum() or c in ('_', '-', ' ')
        ).strip()
        if not filename:
            filename = 'ai_analyst_export'

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        full_filename = f'{filename}_{timestamp}.csv'

        # Get the last tool result from the conversation context
        # The gateway will inject the last result into the tool call context
        # For now, we'll look at the most recent tool call log for this user's conversation
        last_log = env['ai.analyst.tool.call.log'].sudo().search([
            ('user_id', '=', user.id),
            ('success', '=', True),
            ('tool_name', '!=', 'export_csv'),
        ], order='create_date desc', limit=1)

        if not last_log or not last_log.result_summary:
            return {
                'error': 'No previous data found to export. Please run a query first.'
            }

        try:
            data = json.loads(last_log.result_summary)
        except (json.JSONDecodeError, TypeError):
            return {
                'error': 'Could not parse the previous result data for CSV export.'
            }

        # Find the tabular data in the result
        rows, headers = self._extract_tabular_data(data)

        if not rows:
            return {
                'error': 'No tabular data found in the previous result to export.'
            }

        # Generate CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

        csv_content = output.getvalue()
        csv_bytes = csv_content.encode('utf-8-sig')  # BOM for Excel compatibility
        csv_base64 = base64.b64encode(csv_bytes).decode('ascii')

        # Create ir.attachment
        attachment = env['ir.attachment'].sudo().create({
            'name': full_filename,
            'datas': csv_base64,
            'res_model': 'ai.analyst.tool.call.log',
            'res_id': last_log.id,
            'mimetype': 'text/csv',
            'type': 'binary',
        })

        return {
            'success': True,
            'filename': full_filename,
            'attachment_id': attachment.id,
            'row_count': len(rows),
            'download_url': f'/web/content/{attachment.id}?download=true',
        }

    def _extract_tabular_data(self, data):
        """Extract rows and headers from various result structures.

        Tools return data in different shapes. This method handles:
        - data['data'] (list of dicts)
        - data['breakdown'] (list of dicts)
        - data['by_partner'] / data['by_vendor'] (list of dicts)
        - data['rows'] (list of dicts)
        """
        rows = []
        headers = []

        # Try common data keys
        for key in ['data', 'breakdown', 'by_partner', 'by_vendor', 'rows',
                     'by_config', 'time_series']:
            candidate = data.get(key)
            if isinstance(candidate, list) and candidate:
                if isinstance(candidate[0], dict):
                    rows = candidate
                    headers = list(candidate[0].keys())
                    return rows, headers
                # Handle nested time_series (dict of lists)
                elif isinstance(candidate, dict):
                    for sub_key, sub_list in candidate.items():
                        if isinstance(sub_list, list) and sub_list and isinstance(sub_list[0], dict):
                            rows = sub_list
                            headers = list(sub_list[0].keys())
                            return rows, headers

        # Try time_series specifically (it's a dict with 'online' and 'pos' keys)
        ts = data.get('time_series')
        if isinstance(ts, dict):
            for channel, series in ts.items():
                if isinstance(series, list) and series and isinstance(series[0], dict):
                    for item in series:
                        item['channel'] = channel
                    rows.extend(series)
            if rows:
                headers = list(rows[0].keys())
                return rows, headers

        # If nothing found, try to flatten the summary
        summary = data.get('summary')
        if isinstance(summary, dict):
            rows = [summary]
            headers = list(summary.keys())
            return rows, headers

        return rows, headers
