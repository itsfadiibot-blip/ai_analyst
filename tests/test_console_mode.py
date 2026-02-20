# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConsoleMode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_1 = cls.env['res.users'].create({
            'name': 'Console User 1',
            'login': 'console_user_1',
            'email': 'console1@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })
        cls.user_2 = cls.env['res.users'].create({
            'name': 'Console User 2',
            'login': 'console_user_2',
            'email': 'console2@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })

    def test_toggle_updates_user_field(self):
        self.assertFalse(self.user_1.ai_console_mode)
        self.user_1.with_user(self.user_1).write({'ai_console_mode': True})
        self.assertTrue(self.user_1.with_user(self.user_1).ai_console_mode)
        self.user_1.with_user(self.user_1).write({'ai_console_mode': False})
        self.assertFalse(self.user_1.with_user(self.user_1).ai_console_mode)

    def test_user_cannot_change_other_user_preference(self):
        with self.assertRaises(AccessError):
            self.user_1.with_user(self.user_2).write({'ai_console_mode': True})
