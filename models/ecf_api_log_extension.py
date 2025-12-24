# -*- coding: utf-8 -*-
"""
Extensión del modelo ecf.api.log de l10n_do_e_cf_tests para agregar
relación con account.move (facturas).
"""
from odoo import api, fields, models, _


class EcfApiLogExtension(models.Model):
    """Extiende ecf.api.log para agregar relación con facturas."""
    _inherit = 'ecf.api.log'

    # Relación con factura
    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        ondelete='set null',
        index=True,
        help='Factura relacionada con esta transacción API'
    )

    def action_view_move(self):
        """Abre la factura relacionada."""
        self.ensure_one()
        if not self.move_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
