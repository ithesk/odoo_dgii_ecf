# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class EcfCreditApplication(models.Model):
    """
    Modelo para registrar las aplicaciones de créditos de NC en facturas.
    Permite auditar y rastrear el uso de cada crédito.
    """
    _name = 'l10n_do.ecf_credit_application'
    _description = 'Aplicación de Crédito NC'
    _order = 'date_applied desc, id desc'

    # ========== CAMPOS PRINCIPALES ==========
    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True,
    )

    credit_id = fields.Many2one(
        'l10n_do.ecf_credit',
        string='Crédito',
        required=True,
        ondelete='restrict',
        index=True,
        help='Crédito de NC que se está aplicando'
    )

    invoice_move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('move_type', '=', 'out_invoice')]",
        help='Factura donde se aplica el crédito'
    )

    # ========== CAMPOS RELACIONADOS ==========
    credit_encf = fields.Char(
        string='e-NCF Crédito',
        related='credit_id.encf',
        store=True,
    )

    invoice_encf = fields.Char(
        string='e-NCF Factura',
        related='invoice_move_id.encf',
        store=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='credit_id.partner_id',
        store=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='credit_id.company_id',
        store=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='credit_id.currency_id',
        store=True,
    )

    # ========== MONTOS ==========
    amount_applied = fields.Monetary(
        string='Monto Aplicado',
        required=True,
        currency_field='currency_id',
        help='Monto del crédito aplicado a la factura'
    )

    # ========== ESTADO ==========
    state = fields.Selection(
        selection=[
            ('applied', 'Aplicado'),
            ('reversed', 'Revertido'),
        ],
        string='Estado',
        default='applied',
        required=True,
        help='Estado de la aplicación:\n'
             '- Aplicado: El crédito está aplicado a la factura\n'
             '- Revertido: La aplicación fue revertida'
    )

    # ========== FECHAS Y AUDITORÍA ==========
    date_applied = fields.Datetime(
        string='Fecha de Aplicación',
        default=fields.Datetime.now,
        required=True,
    )

    date_reversed = fields.Datetime(
        string='Fecha de Reversión',
    )

    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user,
        required=True,
        help='Usuario que realizó la aplicación'
    )

    reversed_by_id = fields.Many2one(
        'res.users',
        string='Revertido por',
        help='Usuario que revirtió la aplicación'
    )

    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre la aplicación'
    )

    # ========== CAMPOS COMPUTADOS ==========
    @api.depends('credit_encf', 'invoice_encf')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.credit_encf or '?'} → {record.invoice_encf or '?'}"

    # ========== CONSTRAINTS ==========
    @api.constrains('amount_applied')
    def _check_amount_applied(self):
        for record in self:
            if record.amount_applied <= 0:
                raise UserError(_(
                    'El monto aplicado debe ser mayor a cero.'
                ))

    @api.constrains('credit_id', 'invoice_move_id')
    def _check_same_partner(self):
        for record in self:
            if record.credit_id.partner_id != record.invoice_move_id.partner_id:
                raise UserError(_(
                    'El crédito y la factura deben pertenecer al mismo cliente.'
                ))

    _sql_constraints = [
        ('positive_amount', 'CHECK(amount_applied > 0)',
         'El monto aplicado debe ser positivo.'),
    ]

    # ========== MÉTODOS DE NEGOCIO ==========
    def action_reverse(self):
        """Revierte la aplicación del crédito."""
        for record in self:
            if record.state == 'reversed':
                raise UserError(_(
                    'Esta aplicación ya fue revertida.'
                ))

            record.credit_id.reverse_application(record)
            record.date_reversed = fields.Datetime.now()
            record.reversed_by_id = self.env.user

    # ========== ACCIONES DE VISTA ==========
    def action_view_credit(self):
        """Abre el crédito asociado."""
        self.ensure_one()
        return {
            'name': _('Crédito'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_do.ecf_credit',
            'view_mode': 'form',
            'res_id': self.credit_id.id,
        }

    def action_view_invoice(self):
        """Abre la factura asociada."""
        self.ensure_one()
        return {
            'name': _('Factura'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_move_id.id,
        }
