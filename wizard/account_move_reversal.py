# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta


class AccountMoveReversal(models.TransientModel):
    """
    Extensión del wizard de reversión de Odoo para agregar campos DGII
    requeridos en Notas de Crédito electrónicas de República Dominicana.
    """
    _inherit = 'account.move.reversal'

    # ========== CAMPOS DGII PARA NC ==========
    x_codigo_modificacion = fields.Selection(
        selection=[
            ('1', '1 - Anulación total'),
            ('2', '2 - Corrección de monto'),
            ('3', '3 - Corrección de datos del comprador'),
            ('4', '4 - Cambio de NCF por error en secuencia'),
            ('5', '5 - Reemplazo por error en información'),
        ],
        string='Código de Modificación',
        default='1',
        help='Código de modificación según DGII para NC tipo 34'
    )

    x_es_nc_electronica = fields.Boolean(
        string='Es NC Electrónica',
        compute='_compute_es_nc_electronica',
        help='Indica si la NC será electrónica (factura original tiene e-NCF)'
    )

    x_dias_desde_factura = fields.Integer(
        string='Días desde Factura',
        compute='_compute_dias_desde_factura',
        help='Días transcurridos desde la fecha de la factura original'
    )

    x_indicador_nota_credito = fields.Selection(
        selection=[
            ('0', '0 - Dentro de 30 días'),
            ('1', '1 - Más de 30 días'),
        ],
        string='Indicador NC',
        compute='_compute_indicador_nc',
        help='Indicador de Nota de Crédito según días transcurridos'
    )

    x_advertencia_30_dias = fields.Char(
        string='Advertencia',
        compute='_compute_advertencia_30_dias',
    )

    # ========== CAMPOS COMPUTADOS ==========
    @api.depends('move_ids')
    def _compute_es_nc_electronica(self):
        for record in self:
            # Es NC electrónica si alguna factura tiene e-NCF
            record.x_es_nc_electronica = any(
                move.encf for move in record.move_ids
                if move.move_type == 'out_invoice'
            )

    @api.depends('move_ids', 'date')
    def _compute_dias_desde_factura(self):
        for record in self:
            if record.move_ids and record.date:
                # Tomar la fecha más antigua de las facturas
                oldest_date = min(
                    move.invoice_date or move.date
                    for move in record.move_ids
                )
                if oldest_date:
                    record.x_dias_desde_factura = (record.date - oldest_date).days
                else:
                    record.x_dias_desde_factura = 0
            else:
                record.x_dias_desde_factura = 0

    @api.depends('x_dias_desde_factura')
    def _compute_indicador_nc(self):
        for record in self:
            if record.x_dias_desde_factura > 30:
                record.x_indicador_nota_credito = '1'
            else:
                record.x_indicador_nota_credito = '0'

    @api.depends('x_dias_desde_factura', 'x_es_nc_electronica')
    def _compute_advertencia_30_dias(self):
        for record in self:
            if record.x_es_nc_electronica and record.x_dias_desde_factura > 30:
                record.x_advertencia_30_dias = _(
                    '⚠️ Han pasado %d días desde la factura original. '
                    'El indicador de NC será 1 (más de 30 días).'
                ) % record.x_dias_desde_factura
            else:
                record.x_advertencia_30_dias = False

    # ========== MÉTODOS OVERRIDE ==========
    def _prepare_default_reversal(self, move):
        """Extiende la preparación de la NC para agregar campos DGII."""
        res = super()._prepare_default_reversal(move)

        # Solo agregar campos DGII si es factura de cliente con e-NCF
        if move.move_type == 'out_invoice' and move.encf:
            res.update({
                'x_ref_move_id': move.id,
                'x_ncf_modificado': move.encf,
                'x_fecha_ncf_modificado': move.invoice_date or move.date,
                'x_codigo_modificacion': self.x_codigo_modificacion,
                'x_razon_modificacion': self.reason,
            })

        return res

    def reverse_moves(self, is_modify=False):
        """Override para validar campos DGII antes de crear la NC."""
        # Validar que se haya seleccionado código de modificación para NC electrónicas
        if self.x_es_nc_electronica and not self.x_codigo_modificacion:
            raise UserError(_(
                'Debe seleccionar un Código de Modificación para la Nota de Crédito electrónica.'
            ))

        return super().reverse_moves(is_modify=is_modify)
