# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class EcfCredit(models.Model):
    """
    Modelo para gestionar el saldo de crédito de Notas de Crédito e-CF tipo 34.
    Permite rastrear el monto disponible y las aplicaciones realizadas.
    """
    _name = 'l10n_do.ecf_credit'
    _description = 'Crédito de Nota de Crédito e-CF'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_created desc, id desc'

    # ========== CAMPOS PRINCIPALES ==========
    name = fields.Char(
        string='Referencia',
        compute='_compute_name',
        store=True,
    )

    credit_move_id = fields.Many2one(
        'account.move',
        string='Nota de Crédito',
        required=True,
        ondelete='restrict',
        domain="[('move_type', '=', 'out_refund')]",
        help='Nota de Crédito tipo 34 que origina este crédito'
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        ondelete='restrict',
        help='Cliente al que pertenece el crédito'
    )

    encf = fields.Char(
        string='e-NCF',
        required=True,
        index=True,
        help='Número de comprobante fiscal electrónico de la NC'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='credit_move_id.company_id',
        store=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='credit_move_id.currency_id',
        store=True,
    )

    # ========== MONTOS ==========
    amount_total = fields.Monetary(
        string='Monto Total',
        required=True,
        currency_field='currency_id',
        help='Monto total de la Nota de Crédito'
    )

    amount_available = fields.Monetary(
        string='Saldo Disponible',
        required=True,
        currency_field='currency_id',
        help='Saldo disponible para aplicar en facturas'
    )

    amount_applied = fields.Monetary(
        string='Monto Aplicado',
        compute='_compute_amount_applied',
        store=True,
        currency_field='currency_id',
        help='Suma de montos aplicados en facturas'
    )

    # ========== ESTADO ==========
    state = fields.Selection(
        selection=[
            ('available', 'Disponible'),
            ('partial', 'Parcialmente Usado'),
            ('consumed', 'Consumido'),
            ('void', 'Anulado'),
        ],
        string='Estado',
        default='available',
        required=True,
        tracking=True,
        help='Estado del crédito:\n'
             '- Disponible: Todo el saldo está disponible\n'
             '- Parcialmente Usado: Parte del saldo ha sido aplicado\n'
             '- Consumido: Todo el saldo ha sido utilizado\n'
             '- Anulado: El crédito ha sido anulado'
    )

    # ========== FECHAS ==========
    date_created = fields.Datetime(
        string='Fecha de Creación',
        default=fields.Datetime.now,
        required=True,
    )

    date_expiry = fields.Date(
        string='Fecha de Vencimiento',
        help='Fecha límite para usar el crédito (opcional)'
    )

    # ========== RELACIONES ==========
    application_ids = fields.One2many(
        'l10n_do.ecf_credit_application',
        'credit_id',
        string='Aplicaciones',
        help='Historial de aplicaciones de este crédito'
    )

    application_count = fields.Integer(
        string='# Aplicaciones',
        compute='_compute_application_count',
    )

    # ========== CAMPOS COMPUTADOS ==========
    @api.depends('encf', 'partner_id.name')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.encf or 'Nuevo'} - {record.partner_id.name or ''}"

    @api.depends('application_ids', 'application_ids.amount_applied', 'application_ids.state')
    def _compute_amount_applied(self):
        for record in self:
            applied = sum(
                app.amount_applied
                for app in record.application_ids.filtered(lambda a: a.state == 'applied')
            )
            record.amount_applied = applied

    def _compute_application_count(self):
        for record in self:
            record.application_count = len(record.application_ids)

    # ========== CONSTRAINTS ==========
    @api.constrains('amount_available')
    def _check_amount_available(self):
        for record in self:
            if record.amount_available < 0:
                raise ValidationError(_(
                    'El saldo disponible no puede ser negativo.'
                ))
            if record.amount_available > record.amount_total:
                raise ValidationError(_(
                    'El saldo disponible no puede ser mayor al monto total.'
                ))

    _sql_constraints = [
        ('encf_company_unique', 'UNIQUE(encf, company_id)',
         'Ya existe un crédito con este e-NCF en la compañía.'),
    ]

    # ========== MÉTODOS DE NEGOCIO ==========
    def apply_credit(self, invoice_move, amount, user=None):
        """
        Aplica un monto del crédito a una factura.

        Args:
            invoice_move: account.move de la factura donde aplicar
            amount: Monto a aplicar
            user: Usuario que realiza la operación (opcional)

        Returns:
            l10n_do.ecf_credit_application creado

        Raises:
            UserError: Si no hay saldo suficiente o el crédito no está disponible
        """
        self.ensure_one()

        # Validaciones
        if self.state == 'void':
            raise UserError(_(
                'No se puede aplicar un crédito anulado.'
            ))

        if self.state == 'consumed':
            raise UserError(_(
                'Este crédito ya ha sido consumido completamente.'
            ))

        if amount <= 0:
            raise UserError(_(
                'El monto a aplicar debe ser mayor a cero.'
            ))

        if amount > self.amount_available:
            raise UserError(_(
                'El monto a aplicar (%(amount)s) excede el saldo disponible (%(available)s).',
                amount=amount,
                available=self.amount_available
            ))

        if invoice_move.partner_id != self.partner_id:
            raise UserError(_(
                'El crédito pertenece a %(credit_partner)s pero la factura es de %(invoice_partner)s.',
                credit_partner=self.partner_id.name,
                invoice_partner=invoice_move.partner_id.name
            ))

        # Crear aplicación con bloqueo pesimista
        self.env.cr.execute(
            "SELECT id FROM l10n_do_ecf_credit WHERE id = %s FOR UPDATE NOWAIT",
            [self.id]
        )

        application = self.env['l10n_do.ecf_credit_application'].create({
            'credit_id': self.id,
            'invoice_move_id': invoice_move.id,
            'amount_applied': amount,
            'user_id': user.id if user else self.env.user.id,
        })

        # Actualizar saldo
        self.amount_available -= amount
        self._update_state()

        # ========== CONCILIACIÓN CONTABLE ==========
        # Buscar las líneas de cuenta por cobrar de la factura y la NC
        # para conciliarlas y que el estado de pago se actualice correctamente
        try:
            self._reconcile_credit_with_invoice(invoice_move, amount)
        except Exception as e:
            # Si falla la conciliación, registrar pero no bloquear
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "No se pudo conciliar automáticamente NC %s con factura %s: %s",
                self.credit_move_id.name, invoice_move.name, str(e)
            )

        return application

    def _reconcile_credit_with_invoice(self, invoice_move, amount):
        """
        Concilia los apuntes contables de la NC con la factura.
        Esto actualiza el estado de pago de la factura correctamente.

        Args:
            invoice_move: Factura donde se aplica el crédito
            amount: Monto a conciliar
        """
        self.ensure_one()

        # Obtener cuenta por cobrar (receivable)
        receivable_account = invoice_move.partner_id.property_account_receivable_id

        if not receivable_account:
            return

        # Línea de la factura (débito en cuenta por cobrar)
        invoice_receivable_lines = invoice_move.line_ids.filtered(
            lambda l: l.account_id == receivable_account
            and l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
        )

        # Línea de la NC (crédito en cuenta por cobrar)
        credit_note = self.credit_move_id
        nc_receivable_lines = credit_note.line_ids.filtered(
            lambda l: l.account_id == receivable_account
            and l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
        )

        if not invoice_receivable_lines or not nc_receivable_lines:
            return

        # Conciliar las líneas
        lines_to_reconcile = invoice_receivable_lines + nc_receivable_lines

        if lines_to_reconcile:
            lines_to_reconcile.reconcile()

    def reverse_application(self, application):
        """
        Revierte una aplicación de crédito.

        Args:
            application: l10n_do.ecf_credit_application a revertir
        """
        self.ensure_one()

        if application.credit_id != self:
            raise UserError(_(
                'La aplicación no pertenece a este crédito.'
            ))

        if application.state == 'reversed':
            raise UserError(_(
                'Esta aplicación ya fue revertida.'
            ))

        # Devolver saldo
        self.amount_available += application.amount_applied
        application.state = 'reversed'
        self._update_state()

    def _update_state(self):
        """Actualiza el estado basado en el saldo disponible."""
        self.ensure_one()

        if self.state == 'void':
            return

        if self.amount_available <= 0:
            self.state = 'consumed'
        elif self.amount_available < self.amount_total:
            self.state = 'partial'
        else:
            self.state = 'available'

    def action_void(self):
        """Anula el crédito."""
        for record in self:
            if record.amount_applied > 0:
                raise UserError(_(
                    'No se puede anular un crédito que ya tiene aplicaciones. '
                    'Primero revierta las aplicaciones.'
                ))
            record.state = 'void'

    # ========== ACCIONES DE VISTA ==========
    def action_view_applications(self):
        """Abre la vista de aplicaciones de este crédito."""
        self.ensure_one()
        return {
            'name': _('Aplicaciones de Crédito'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_do.ecf_credit_application',
            'view_mode': 'tree,form',
            'domain': [('credit_id', '=', self.id)],
            'context': {'default_credit_id': self.id},
        }

    def action_view_credit_note(self):
        """Abre la Nota de Crédito asociada."""
        self.ensure_one()
        return {
            'name': _('Nota de Crédito'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.credit_move_id.id,
        }
