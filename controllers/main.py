# -*- coding: utf-8 -*-
"""
AI Analyst Controllers â€” HTTP endpoints for the chat interface.
================================================================
"""
import base64
import json
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class AiAnalystController(http.Controller):
    """HTTP controllers for AI Analyst chat interface."""

    # ------------------------------------------------------------------
    # Chat endpoint
    # ------------------------------------------------------------------

    @http.route('/ai_analyst/chat', type='json', auth='user', methods=['POST'])
    def chat(self, conversation_id=None, message='', **kwargs):
        """Process a user chat message and return structured AI response."""
        user = request.env.user
        company = user.company_id

        if not user.has_group('ai_analyst.group_ai_user'):
            return {
                'error': 'You do not have permission to use AI Analyst.',
                'answer': 'Access denied. Please contact your administrator.',
            }

        if not message or not message.strip():
            return {
                'error': 'Please enter a question.',
                'answer': 'Please enter a question.',
            }

        Workspace = request.env['ai.analyst.workspace']
        requested_workspace = False
        requested_workspace_id = kwargs.get('workspace_id')
        if requested_workspace_id:
            requested_workspace = Workspace.browse(int(requested_workspace_id))
            if not requested_workspace.exists() or not requested_workspace.is_active:
                requested_workspace = False

        Conversation = request.env['ai.analyst.conversation']

        # Create or load conversation
        if conversation_id:
            conversation = Conversation.browse(int(conversation_id))
            if not conversation.exists():
                return {'error': 'Conversation not found.', 'answer': 'Conversation not found.'}
            if conversation.user_id.id != user.id:
                return {'error': 'Access denied.', 'answer': 'Access denied.'}

            conversation_workspace = conversation.workspace_id
            if conversation_workspace and (
                not conversation_workspace.exists()
                or not conversation_workspace.is_active
                or not conversation_workspace.user_has_access(user)
            ):
                raise AccessError("You don't have access to that workspace.")

            # Enforce policy: unauthorized requested workspace is ignored.
            if requested_workspace and requested_workspace.user_has_access(user):
                conversation.with_user(user.id).write({'workspace_id': requested_workspace.id})
            elif requested_workspace and requested_workspace.id != (conversation_workspace.id if conversation_workspace else False):
                # Ignore unauthorized workspace_id and keep conversation workspace.
                pass

        else:
            if requested_workspace and not requested_workspace.user_has_access(user):
                raise AccessError("You don't have access to that workspace.")

            vals = {
                'user_id': user.id,
                'company_id': company.id,
            }
            if requested_workspace:
                vals['workspace_id'] = requested_workspace.id
            conversation = Conversation.create(vals)

        # Final guard before gateway call (no privilege escalation).
        if conversation.workspace_id and not conversation.workspace_id.user_has_access(user):
            raise AccessError("You don't have access to that workspace.")

        try:
            gateway = request.env['ai.analyst.gateway']
            result = gateway.process_message(
                conversation_id=conversation.id,
                user_message=message.strip(),
                user_id=user.id,
            )
            result['conversation_id'] = conversation.id
            return result

        except AccessError as e:
            _logger.warning('Access error in chat: %s', str(e))
            return {
                'error': str(e),
                'answer': str(e),
                'conversation_id': conversation.id,
            }
        except Exception:
            _logger.exception('Error in chat endpoint')
            return {
                'error': 'An unexpected error occurred.',
                'answer': 'An unexpected error occurred. Please try again.',
                'conversation_id': conversation.id,
            }

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    @http.route('/ai_analyst/conversations', type='json', auth='user', methods=['POST'])
    def list_conversations(self, **kwargs):
        """List the current user's conversations."""
        user = request.env.user
        conversations = request.env['ai.analyst.conversation'].search_read(
            [
                ('user_id', '=', user.id),
                ('state', '=', 'active'),
            ],
            fields=['id', 'name', 'write_date', 'message_count'],
            order='write_date desc',
            limit=50,
        )
        return {'conversations': conversations}

    @http.route('/ai_analyst/conversation/messages', type='json', auth='user', methods=['POST'])
    def get_conversation_messages(self, conversation_id, **kwargs):
        """Get all messages for a conversation."""
        user = request.env.user
        conversation = request.env['ai.analyst.conversation'].browse(int(conversation_id))

        if not conversation.exists() or conversation.user_id.id != user.id:
            return {'error': 'Conversation not found or access denied.'}

        messages = request.env['ai.analyst.message'].search_read(
            [('conversation_id', '=', conversation.id)],
            fields=['role', 'content', 'structured_response', 'create_date',
                    'tokens_input', 'tokens_output', 'processing_time_ms', 'provider_model'],
            order='create_date asc',
        )

        for msg in messages:
            if msg.get('structured_response'):
                try:
                    msg['structured_response'] = json.loads(msg['structured_response'])
                except (json.JSONDecodeError, TypeError):
                    msg['structured_response'] = None

        return {
            'conversation_id': conversation.id,
            'name': conversation.name,
            'messages': messages,
        }

    @http.route('/ai_analyst/conversation/archive', type='json', auth='user', methods=['POST'])
    def archive_conversation(self, conversation_id, **kwargs):
        """Archive a conversation."""
        user = request.env.user
        conversation = request.env['ai.analyst.conversation'].browse(int(conversation_id))

        if not conversation.exists() or conversation.user_id.id != user.id:
            return {'error': 'Conversation not found or access denied.'}

        conversation.action_archive()
        return {'success': True}

    # ------------------------------------------------------------------
    # Saved reports
    # ------------------------------------------------------------------

    @http.route('/ai_analyst/save_report', type='json', auth='user', methods=['POST'])
    def save_report(self, conversation_id, message_id, name='', **kwargs):
        """Save a message result as a report."""
        user = request.env.user

        message = request.env['ai.analyst.message'].browse(int(message_id))
        if not message.exists():
            return {'error': 'Message not found.'}

        conversation = message.conversation_id
        if conversation.user_id.id != user.id:
            return {'error': 'Access denied.'}

        user_query = ''
        prev_msgs = request.env['ai.analyst.message'].search([
            ('conversation_id', '=', conversation.id),
            ('role', '=', 'user'),
            ('create_date', '<=', message.create_date),
        ], order='create_date desc', limit=1)
        if prev_msgs:
            user_query = prev_msgs.content or ''

        report_name = name or user_query[:80] or f'Report #{message.id}'

        structured = {}
        tool_name = ''
        tool_args = {}
        try:
            structured = json.loads(message.structured_response or '{}')
        except Exception:
            structured = {}
        tool_calls = ((structured.get('meta') or {}).get('tool_calls') or []) if isinstance(structured, dict) else []
        if tool_calls:
            first = tool_calls[0] or {}
            tool_name = first.get('tool') or ''
            tool_args = first.get('params') or {}

        report = request.env['ai.analyst.saved.report'].create({
            'name': report_name,
            'conversation_id': conversation.id,
            'message_id': message.id,
            'user_query': user_query,
            'structured_response': message.structured_response,
            'tool_name': tool_name,
            'tool_args_json': json.dumps(tool_args, default=str),
            'user_id': user.id,
            'company_id': user.company_id.id,
        })

        return {
            'success': True,
            'report_id': report.id,
            'name': report.name,
        }

    @http.route('/ai_analyst/pin_to_dashboard', type='json', auth='user', methods=['POST'])
    def pin_to_dashboard(self, report_id, **kwargs):
        """Pin a saved report to dashboard as dynamic widget (tool + args only)."""
        user = request.env.user
        report = request.env['ai.analyst.saved.report'].browse(int(report_id))

        if not report.exists() or report.user_id.id != user.id:
            return {'error': 'Report not found or access denied.'}

        if not report.tool_name:
            return {'error': 'This report cannot be pinned dynamically (missing tool metadata).'}

        dashboard = request.env['ai.analyst.dashboard'].with_user(user.id).get_or_create_default(user)

        report.with_user(user.id).write({'is_pinned': True})

        widget = request.env['ai.analyst.dashboard.widget'].with_user(user.id).create({
            'dashboard_id': dashboard.id,
            'user_id': user.id,
            'company_id': user.company_id.id,
            'tool_name': report.tool_name,
            'tool_args_json': report.tool_args_json or '{}',
            'title': report.name or report.user_query or 'Dashboard Widget',
            'sequence': 10,
            'width': 6,
            'height': 4,
            'refresh_interval_seconds': 300,
            'active': True,
        })

        return {
            'success': True,
            'dashboard_id': dashboard.id,
            'widget_id': widget.id,
        }

    @http.route('/ai_analyst/boss_export/status', type='json', auth='user', methods=['POST'])
    def boss_export_status(self, job_id=None, job_token=None, **kwargs):
        user = request.env.user
        domain = [('requested_by', '=', user.id)]
        if job_id:
            domain.append(('id', '=', int(job_id)))
        elif job_token:
            domain.append(('job_token', '=', str(job_token)))
        else:
            return {'error': 'Missing job_id or job_token.'}

        job = request.env['ai.analyst.boss.export.job'].search(domain, limit=1)
        if not job:
            return {'error': 'Export job not found.'}

        if job.state == 'queued':
            job.action_process()

        return {
            'job_id': job.id,
            'job_token': job.job_token,
            'state': job.state,
            'progress_percent': job.progress_percent,
            'processed_rows': job.processed_rows,
            'total_rows': job.total_rows,
            'filename': job.csv_filename,
            'error': job.error_message or False,
        }

    @http.route('/ai_analyst/boss_export/download', type='http', auth='user', methods=['GET'])
    def boss_export_download(self, job_token=None, **kwargs):
        user = request.env.user
        if not job_token:
            return request.not_found()
        job = request.env['ai.analyst.boss.export.job'].search([
            ('job_token', '=', job_token),
            ('requested_by', '=', user.id),
        ], limit=1)
        if not job or job.state != 'completed' or not job.csv_content:
            return request.not_found()

        content = base64.b64decode(job.csv_content)
        headers = [
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Disposition', 'attachment; filename="%s"' % (job.csv_filename or 'boss_open_query.csv')),
        ]
        return request.make_response(content, headers=headers)


    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    @http.route('/ai_analyst/workspaces', type='json', auth='user', methods=['POST'])
    def list_workspaces(self, **kwargs):
        """List workspaces accessible to the current user."""
        user = request.env.user
        if not user.has_group('ai_analyst.group_ai_user'):
            return {'workspaces': []}

        workspace_model = request.env['ai.analyst.workspace']
        all_workspaces = workspace_model.get_accessible_workspaces(user=user)

        workspaces = [{
            'id': ws.id,
            'name': ws.name,
            'code': ws.code,
            'icon': ws.icon or 'fa-briefcase',
            'color': ws.color,
        } for ws in all_workspaces]

        return {'workspaces': workspaces}

    @http.route('/ai_analyst/workspace/context', type='json', auth='user', methods=['POST'])
    def get_workspace_context(self, workspace_id, **kwargs):
        """Get workspace context: prompts and tool names for the UI."""
        user = request.env.user
        workspace = request.env['ai.analyst.workspace'].browse(int(workspace_id))

        if not workspace.exists() or not workspace.is_active:
            return {'error': 'Workspace not found.'}
        if not workspace.user_has_access(user):
            raise AccessError("You don't have access to that workspace.")

        prompt_packs = workspace.get_prompt_packs()
        prompts = []
        for category, items in prompt_packs.items():
            for item in items:
                prompts.append({
                    'category': category,
                    'text': item['text'],
                    'description': item['description'],
                    'icon': item['icon'],
                })

        tool_names = list(workspace.get_allowed_tool_names())

        return {
            'workspace_id': workspace.id,
            'name': workspace.name,
            'code': workspace.code,
            'prompts': prompts,
            'tool_names': tool_names,
            'dashboard_id': workspace.default_dashboard_id.id if workspace.default_dashboard_id else None,
        }

