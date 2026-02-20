# -*- coding: utf-8 -*-

from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestWorkspaceAccessControl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace_model = cls.env['ai.analyst.workspace']

        cls.admin = cls.env.ref('base.user_admin')
        cls.sales_group = cls.env.ref('ai_analyst.group_ai_sales_user')
        cls.buying_group = cls.env.ref('ai_analyst.group_ai_buying_user')

        cls.sales_user = cls.env['res.users'].create({
            'name': 'Sales Workspace User',
            'login': 'sales_workspace_user',
            'email': 'sales_workspace_user@test.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('ai_analyst.group_ai_user').id,
                cls.sales_group.id,
            ])],
        })

        cls.sales_ws = cls.env.ref('ai_analyst.workspace_sales')
        cls.buying_ws = cls.env.ref('ai_analyst.workspace_buying')
        cls.all_tools_ws = cls.env.ref('ai_analyst.workspace_all_tools')

    def test_admin_can_see_all_workspaces(self):
        workspaces = self.workspace_model.with_user(self.admin).get_accessible_workspaces(user=self.admin)
        self.assertIn(self.sales_ws.id, workspaces.ids)
        self.assertIn(self.buying_ws.id, workspaces.ids)
        self.assertIn(self.all_tools_ws.id, workspaces.ids)

    def test_sales_user_only_accesses_sales(self):
        workspaces = self.workspace_model.with_user(self.sales_user).get_accessible_workspaces(user=self.sales_user)
        self.assertIn(self.sales_ws.id, workspaces.ids)
        self.assertNotIn(self.buying_ws.id, workspaces.ids)
        self.assertFalse(self.buying_ws.user_has_access(self.sales_user))

    def test_all_tools_hidden_for_non_admin_even_if_misconfigured(self):
        self.all_tools_ws.sudo().write({'required_group_ids': [(6, 0, [self.sales_group.id])]})

        # Model-level policy still denies non-admin access.
        self.assertFalse(self.all_tools_ws.user_has_access(self.sales_user))

        # Record rule policy also keeps it hidden from search/listing.
        visible = self.workspace_model.with_user(self.sales_user).search([])
        self.assertNotIn(self.all_tools_ws.id, visible.ids)

    def test_chat_rejects_unauthorized_workspace_on_new_conversation(self):
        from odoo.addons.ai_analyst.controllers.main import AiAnalystController

        controller = AiAnalystController()
        fake_request = SimpleNamespace(env=self.env(user=self.sales_user.id))

        with patch('odoo.addons.ai_analyst.controllers.main.request', fake_request):
            with self.assertRaises(AccessError):
                controller.chat(message='hello', workspace_id=self.buying_ws.id)

    def test_chat_ignores_unauthorized_workspace_on_existing_conversation(self):
        from odoo.addons.ai_analyst.controllers.main import AiAnalystController

        controller = AiAnalystController()
        conv = self.env['ai.analyst.conversation'].with_user(self.sales_user).create({
            'user_id': self.sales_user.id,
            'company_id': self.sales_user.company_id.id,
            'workspace_id': self.sales_ws.id,
        })

        fake_request = SimpleNamespace(env=self.env(user=self.sales_user.id))

        with patch('odoo.addons.ai_analyst.controllers.main.request', fake_request), \
             patch('odoo.addons.ai_analyst.models.ai_analyst_gateway.AiAnalystGateway.process_message', return_value={'answer': 'ok'}):
            result = controller.chat(
                conversation_id=conv.id,
                message='hello',
                workspace_id=self.buying_ws.id,
            )

        self.assertEqual(result.get('answer'), 'ok')
        self.assertEqual(conv.workspace_id.id, self.sales_ws.id)
