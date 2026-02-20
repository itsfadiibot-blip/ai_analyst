# -*- coding: utf-8 -*-
"""
Security tests for AI Analyst module.
========================================
Tests multi-company isolation, record rules, and access controls.
"""
import logging

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestMultiCompanyIsolation(TransactionCase):
    """Test that conversations are isolated per company."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create two companies
        cls.company_a = cls.env['res.company'].create({'name': 'Company A'})
        cls.company_b = cls.env['res.company'].create({'name': 'Company B'})

        # Create users for each company
        cls.user_a = cls.env['res.users'].create({
            'name': 'User A',
            'login': 'ai_test_user_a',
            'email': 'usera@test.com',
            'company_id': cls.company_a.id,
            'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })
        cls.user_b = cls.env['res.users'].create({
            'name': 'User B',
            'login': 'ai_test_user_b',
            'email': 'userb@test.com',
            'company_id': cls.company_b.id,
            'company_ids': [(6, 0, [cls.company_b.id])],
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })

        # Create conversations
        cls.conv_a = cls.env['ai.analyst.conversation'].with_user(cls.user_a).create({
            'user_id': cls.user_a.id,
            'company_id': cls.company_a.id,
        })
        cls.conv_b = cls.env['ai.analyst.conversation'].with_user(cls.user_b).create({
            'user_id': cls.user_b.id,
            'company_id': cls.company_b.id,
        })

    def test_user_a_cannot_see_user_b_conversation(self):
        """User A should not see User B's conversations."""
        convs = self.env['ai.analyst.conversation'].with_user(self.user_a).search([])
        conv_ids = convs.ids
        self.assertIn(self.conv_a.id, conv_ids)
        self.assertNotIn(self.conv_b.id, conv_ids)

    def test_user_b_cannot_see_user_a_conversation(self):
        """User B should not see User A's conversations."""
        convs = self.env['ai.analyst.conversation'].with_user(self.user_b).search([])
        conv_ids = convs.ids
        self.assertIn(self.conv_b.id, conv_ids)
        self.assertNotIn(self.conv_a.id, conv_ids)


@tagged('post_install', '-at_install')
class TestRecordRules(TransactionCase):
    """Test record rules for own-record isolation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_1 = cls.env['res.users'].create({
            'name': 'AI User 1',
            'login': 'ai_test_user_1',
            'email': 'user1@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })
        cls.user_2 = cls.env['res.users'].create({
            'name': 'AI User 2',
            'login': 'ai_test_user_2',
            'email': 'user2@test.com',
            'groups_id': [(4, cls.env.ref('ai_analyst.group_ai_user').id)],
        })

    def test_user_sees_only_own_conversations(self):
        """Regular AI users see only their own conversations."""
        conv_1 = self.env['ai.analyst.conversation'].with_user(self.user_1).create({
            'user_id': self.user_1.id,
            'company_id': self.user_1.company_id.id,
        })
        conv_2 = self.env['ai.analyst.conversation'].with_user(self.user_2).create({
            'user_id': self.user_2.id,
            'company_id': self.user_2.company_id.id,
        })

        user_1_convs = self.env['ai.analyst.conversation'].with_user(
            self.user_1
        ).search([]).ids
        self.assertIn(conv_1.id, user_1_convs)
        self.assertNotIn(conv_2.id, user_1_convs)

    def test_saved_report_isolation(self):
        """Users can only see their own saved reports."""
        report_1 = self.env['ai.analyst.saved.report'].with_user(self.user_1).create({
            'name': 'User 1 Report',
            'user_id': self.user_1.id,
            'company_id': self.user_1.company_id.id,
        })
        report_2 = self.env['ai.analyst.saved.report'].with_user(self.user_2).create({
            'name': 'User 2 Report',
            'user_id': self.user_2.id,
            'company_id': self.user_2.company_id.id,
        })

        user_1_reports = self.env['ai.analyst.saved.report'].with_user(
            self.user_1
        ).search([]).ids
        self.assertIn(report_1.id, user_1_reports)
        self.assertNotIn(report_2.id, user_1_reports)
