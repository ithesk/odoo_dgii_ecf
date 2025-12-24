# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ApplyCreditWizard(models.TransientModel):
    """
    Wizard para aplicar créditos de NC a una factura.
    Permite buscar NC disponibles y aplicar un monto específico.
    """
    _name = 'account.move.apply.credit.wizard'
    _description = 'Aplicar Crédito de NC'

    # ========== FACTURA DESTINO ==========
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        readonly=True,
        domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]",
        help='Factura donde se aplicará el crédito'
    )

    invoice_encf = fields.Char(
        string='e-NCF Factura',
        related='invoice_id.encf',
        readonly=True,
    )

    invoice_amount = fields.Monetary(
        string='Monto Factura',
        related='invoice_id.amount_total',
        readonly=True,
    )

    invoice_residual = fields.Monetary(
        string='Saldo Pendiente',
        related='invoice_id.amount_residual',
        readonly=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='invoice_id.partner_id',
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='invoice_id.company_id',
        readonly=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='invoice_id.currency_id',
        readonly=True,
    )

    # ========== CRÉDITO A APLICAR ==========
    credit_id = fields.Many2one(
        'l10n_do.ecf_credit',
        string='Nota de Crédito',
        required=True,
        domain="[('partner_id', '=', partner_id), ('state', 'in', ['available', 'partial']), ('company_id', '=', company_id)]",
        help='Crédito de NC a aplicar'
    )

    credit_encf = fields.Char(
        string='e-NCF NC',
        related='credit_id.encf',
        readonly=True,
    )

    credit_available = fields.Monetary(
        string='Saldo Disponible NC',
        related='credit_id.amount_available',
        readonly=True,
    )

    # ========== MONTO A APLICAR ==========
    amount_to_apply = fields.Monetary(
        string='Monto a Aplicar',
        required=True,
        currency_field='currency_id',
        help='Monto del crédito a aplicar a la factura'
    )

    # ========== CAMPOS INFORMATIVOS ==========
    available_credits = fields.Many2many(
        'l10n_do.ecf_credit',
        string='Créditos Disponibles',
        compute='_compute_available_credits',
    )

    available_credits_count = fields.Integer(
        string='# Créditos Disponibles',
        compute='_compute_available_credits',
    )

    total_available = fields.Monetary(
        string='Total Créditos Disponibles',
        compute='_compute_available_credits',
        currency_field='currency_id',
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('invoice_id', 'partner_id', 'company_id')
    def _compute_available_credits(self):
        for wizard in self:
            if not wizard.partner_id or not wizard.company_id:
                wizard.available_credits = False
                wizard.available_credits_count = 0
                wizard.total_available = 0.0
                continue

            credits = self.env['l10n_do.ecf_credit'].search([
                ('partner_id', '=', wizard.partner_id.id),
                ('company_id', '=', wizard.company_id.id),
                ('state', 'in', ['available', 'partial']),
                ('amount_available', '>', 0),
            ])
            wizard.available_credits = credits
            wizard.available_credits_count = len(credits)
            wizard.total_available = sum(c.amount_available for c in credits)

    # ========== ONCHANGE ==========
    @api.onchange('credit_id')
    def _onchange_credit_id(self):
        """Sugiere el monto a aplicar."""
        if self.credit_id and self.invoice_id:
            # Sugerir el menor entre saldo disponible y saldo de factura
            self.amount_to_apply = min(
                self.credit_id.amount_available,
                self.invoice_id.amount_residual
            )

    # ========== VALIDACIONES ==========
    @api.constrains('amount_to_apply')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount_to_apply <= 0:
                raise ValidationError(_(
                    'El monto a aplicar debe ser mayor a cero.'
                ))

    # ========== ACCIÓN PRINCIPAL ==========
    def action_apply_credit(self):
        """Aplica el crédito a la factura."""
        self.ensure_one()

        if not self.credit_id:
            raise UserError(_('Debe seleccionar un crédito de NC.'))

        if not self.invoice_id:
            raise UserError(_('No hay factura seleccionada.'))

        if self.amount_to_apply <= 0:
            raise UserError(_('El monto a aplicar debe ser mayor a cero.'))

        if self.amount_to_apply > self.credit_id.amount_available:
            raise UserError(_(
                'El monto a aplicar (%(amount)s) excede el saldo disponible (%(available)s).',
                amount=self.amount_to_apply,
                available=self.credit_id.amount_available
            ))

        if self.amount_to_apply > self.invoice_id.amount_residual:
            raise UserError(_(
                'El monto a aplicar (%(amount)s) excede el saldo pendiente de la factura (%(residual)s).',
                amount=self.amount_to_apply,
                residual=self.invoice_id.amount_residual
            ))

        # Aplicar el crédito
        application = self.credit_id.apply_credit(
            invoice_move=self.invoice_id,
            amount=self.amount_to_apply,
            user=self.env.user,
        )

        # Mensaje de confirmación
        self.invoice_id.message_post(
            body=_(
                'Se aplicó crédito de NC %(encf)s por %(amount)s.\n'
                'Saldo restante del crédito: %(remaining)s',
                encf=self.credit_id.encf,
                amount=self.amount_to_apply,
                remaining=self.credit_id.amount_available
            )
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Crédito Aplicado'),
                'message': _('Se aplicó %s del crédito %s') % (
                    self.amount_to_apply, self.credit_id.encf
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
