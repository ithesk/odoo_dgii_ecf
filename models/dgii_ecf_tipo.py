# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class DgiiEcfTipo(models.Model):
    """
    Catálogo de Tipos de Comprobantes Fiscales Electrónicos según DGII.
    Permite configurar múltiples tipos por diario.
    """
    _name = 'dgii.ecf.tipo'
    _description = 'Tipos de Comprobantes Fiscales Electrónicos DGII'
    _order = 'codigo'

    # ========== CAMPOS BÁSICOS ==========
    codigo = fields.Selection(
        selection=[
            ('31', '31 – Factura de Crédito Fiscal Electrónica'),
            ('32', '32 – Factura de Consumo Electrónica'),
            ('33', '33 – Nota de Débito Electrónica'),
            ('34', '34 – Nota de Crédito Electrónica'),
            ('41', '41 – Comprobante Electrónico de Compras'),
            ('43', '43 – Comprobante Electrónico para Gastos Menores'),
            ('44', '44 – Comprobante Electrónico para Regímenes Especiales'),
            ('45', '45 – Comprobante Electrónico Gubernamental'),
            ('46', '46 – Comprobante Electrónico para Exportaciones'),
            ('47', '47 – Comprobante Electrónico para Pagos al Exterior'),
        ],
        string='Código',
        required=True,
        help='Código del tipo de comprobante según normativa DGII'
    )

    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True,
        help='Nombre completo del tipo de comprobante'
    )

    descripcion = fields.Text(
        string='Descripción',
        help='Descripción detallada del uso de este tipo de comprobante'
    )

    activo = fields.Boolean(
        string='Activo',
        default=True,
        help='Indica si este tipo de comprobante está activo'
    )

    # ========== CLASIFICACIÓN ==========
    es_venta = fields.Boolean(
        string='Es Venta',
        help='Indica si este tipo se usa para operaciones de venta'
    )

    es_compra = fields.Boolean(
        string='Es Compra',
        help='Indica si este tipo se usa para operaciones de compra'
    )

    es_nota_credito = fields.Boolean(
        string='Es Nota de Crédito',
        help='Indica si es un tipo de nota de crédito'
    )

    es_nota_debito = fields.Boolean(
        string='Es Nota de Débito',
        help='Indica si es un tipo de nota de débito'
    )

    requiere_rnc = fields.Boolean(
        string='Requiere RNC',
        default=True,
        help='Indica si este tipo requiere que el cliente tenga RNC'
    )

    # ========== RELACIONES ==========
    journal_ids = fields.Many2many(
        'account.journal',
        'dgii_journal_tipo_ecf_rel',
        'tipo_id',
        'journal_id',
        string='Diarios',
        help='Diarios que pueden usar este tipo de comprobante'
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('codigo')
    def _compute_name(self):
        """Genera el nombre a partir del código."""
        for record in self:
            if record.codigo:
                record.name = dict(record._fields['codigo'].selection).get(record.codigo, record.codigo)
            else:
                record.name = ''

    # ========== CONFIGURACIÓN INICIAL ==========
    @api.model
    def _setup_complete(self):
        """Crea los registros de tipos de e-CF si no existen."""
        super(DgiiEcfTipo, self)._setup_complete()

        tipos_config = [
            {
                'codigo': '31',
                'descripcion': 'Para ventas con derecho a crédito fiscal. Cliente debe tener RNC.',
                'es_venta': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '32',
                'descripcion': 'Para ventas a consumidor final sin RNC.',
                'es_venta': True,
                'requiere_rnc': False,
            },
            {
                'codigo': '33',
                'descripcion': 'Ajuste que incrementa el valor de una factura.',
                'es_nota_debito': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '34',
                'descripcion': 'Ajuste que disminuye el valor de una factura o anula operaciones.',
                'es_nota_credito': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '41',
                'descripcion': 'Para compras a proveedores locales.',
                'es_compra': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '43',
                'descripcion': 'Para gastos menores que no generan crédito fiscal.',
                'es_compra': True,
                'requiere_rnc': False,
            },
            {
                'codigo': '44',
                'descripcion': 'Para contribuyentes en regímenes especiales de tributación.',
                'es_venta': True,
                'requiere_rnc': False,
            },
            {
                'codigo': '45',
                'descripcion': 'Para operaciones con entidades gubernamentales.',
                'es_venta': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '46',
                'descripcion': 'Para ventas de exportación.',
                'es_venta': True,
                'requiere_rnc': True,
            },
            {
                'codigo': '47',
                'descripcion': 'Para servicios facturados a clientes en el exterior.',
                'es_venta': True,
                'requiere_rnc': True,
            },
        ]

        for tipo_data in tipos_config:
            existing = self.search([('codigo', '=', tipo_data['codigo'])], limit=1)
            if not existing:
                self.create(tipo_data)
