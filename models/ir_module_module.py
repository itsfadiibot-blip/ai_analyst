# -*- coding: utf-8 -*-
from odoo import models


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _mark_field_kb_refresh_needed(self):
        self.env['ir.config_parameter'].sudo().set_param('ai_analyst.field_kb_needs_refresh', 'True')

    def button_immediate_install(self):
        res = super().button_immediate_install()
        self._mark_field_kb_refresh_needed()
        return res

    def button_immediate_upgrade(self):
        res = super().button_immediate_upgrade()
        self._mark_field_kb_refresh_needed()
        return res

    def button_immediate_uninstall(self):
        res = super().button_immediate_uninstall()
        self._mark_field_kb_refresh_needed()
        return res
