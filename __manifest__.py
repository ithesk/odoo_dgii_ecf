# -*- coding: utf-8 -*-
{
    'name': 'DGII - Facturación Electrónica RD',
    'version': '19.0.1.4.0',
    'category': 'Accounting/Localizations',
    'summary': 'Módulo de Facturación Electrónica DGII para República Dominicana',
    'description': """
        Módulo de Facturación Electrónica DGII - República Dominicana
        ==============================================================

        Funcionalidades:
        ----------------
        * Gestión de tipos de e-CF (Comprobantes Fiscales Electrónicos)
        * Rangos de secuencias e-NCF con validaciones
        * Generación automática de e-NCF según normativa DGII
        * Validación de RNC mediante API externa (Megaplus)
        * Control de vencimiento de rangos
        * Integración completa con facturación Odoo
        * Gestión de Notas de Crédito tipo 34 con créditos aplicables
        * Aplicación de créditos NC a facturas con FormaPago=7

        Tipos de e-CF soportados:
        -------------------------
        * 31 – Factura de Crédito Fiscal Electrónica
        * 32 – Factura de Consumo Electrónica
        * 33 – Nota de Débito Electrónica
        * 34 – Nota de Crédito Electrónica
        * 41 – Comprobante Electrónico de Compras
        * 43 – Comprobante Electrónico para Gastos Menores
        * 44 – Comprobante Electrónico para Regímenes Especiales
        * 45 – Comprobante Electrónico Gubernamental
        * 46 – Comprobante Electrónico para Exportaciones
        * 47 – Comprobante Electrónico para Pagos al Exterior
    """,
    'author': 'dev ithesk',
    'website': 'https://www.ithesk.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'contacts',
        'mail',
        'l10n_do_e_cf_tests',  # Usa ecf.api.provider y ecf.api.log de este módulo
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data
        'data/ir_cron.xml',

        # Views
        'views/dgii_ecf_tipo_views.xml',
        'views/dgii_ecf_sequence_range_views.xml',
        'views/dgii_transaction_log_views.xml',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/ecf_credit_views.xml',

        # Wizards
        'wizard/account_move_reversal_views.xml',
        'wizard/apply_credit_wizard_views.xml',
        'wizard/create_credit_note_ecf_wizard_views.xml',

        # Reports
        'reports/invoice_dgii_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
