# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    """Extensión del modelo product.template para campos DGII."""
    _inherit = 'product.template'

    # ========== CAMPOS DGII ==========
    x_dgii_bien_servicio = fields.Selection(
        selection=[
            ('1', 'Bien'),
            ('2', 'Servicio'),
        ],
        string='Tipo DGII',
        compute='_compute_dgii_bien_servicio',
        store=True,
        readonly=False,
        help='Indica si es un bien o servicio para facturación electrónica DGII.\n'
             '1 = Bien (producto físico)\n'
             '2 = Servicio'
    )

    x_dgii_unidad_medida = fields.Selection(
        selection=[
            ('1', '1 - Barril'),
            ('2', '2 - Bolsa'),
            ('3', '3 - Botella'),
            ('4', '4 - Bulto'),
            ('5', '5 - Caja'),
            ('6', '6 - Caja de 10 unidades'),
            ('7', '7 - Caja de 100 unidades'),
            ('8', '8 - Caja de 12 unidades'),
            ('9', '9 - Caja de 20 unidades'),
            ('10', '10 - Caja de 24 unidades'),
            ('11', '11 - Caja de 25 unidades'),
            ('12', '12 - Caja de 3 unidades'),
            ('13', '13 - Caja de 4 unidades'),
            ('14', '14 - Caja de 48 unidades'),
            ('15', '15 - Caja de 5 unidades'),
            ('16', '16 - Caja de 50 unidades'),
            ('17', '17 - Caja de 6 unidades'),
            ('18', '18 - Caja de 8 unidades'),
            ('19', '19 - Hora'),
            ('20', '20 - Cubeta'),
            ('21', '21 - Display de 12 unidades'),
            ('22', '22 - Display de 24 unidades'),
            ('23', '23 - Funda'),
            ('24', '24 - Galon'),
            ('25', '25 - Galones de 5 unidades'),
            ('26', '26 - Gramo'),
            ('27', '27 - Juego'),
            ('28', '28 - Kilogramo'),
            ('29', '29 - Kit'),
            ('30', '30 - Lata'),
            ('31', '31 - Libra'),
            ('32', '32 - Litro'),
            ('33', '33 - Metro'),
            ('34', '34 - Millar'),
            ('35', '35 - Mililitro'),
            ('36', '36 - Onza'),
            ('37', '37 - Paca'),
            ('38', '38 - Paquete'),
            ('39', '39 - Pie'),
            ('40', '40 - Pieza'),
            ('41', '41 - Pulgada'),
            ('42', '42 - Resma'),
            ('43', '43 - Unidad'),
            ('44', '44 - Yarda'),
            ('45', '45 - Otro'),
            ('46', '46 - Servicio'),
            ('47', '47 - Tanque'),
            ('48', '48 - Quintal'),
            ('49', '49 - Viaje'),
            ('50', '50 - Dia'),
            ('51', '51 - Mes'),
        ],
        string='Unidad Medida DGII',
        default='43',
        help='Código de unidad de medida según catálogo DGII'
    )

    # ========== MÉTODOS COMPUTADOS ==========
    @api.depends('type')
    def _compute_dgii_bien_servicio(self):
        """Calcula automáticamente si es bien o servicio basado en el tipo de producto."""
        for product in self:
            if product.type == 'service':
                product.x_dgii_bien_servicio = '2'
            else:
                product.x_dgii_bien_servicio = '1'
