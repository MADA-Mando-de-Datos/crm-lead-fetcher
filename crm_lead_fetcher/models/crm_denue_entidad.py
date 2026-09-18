from odoo import fields, models


class CrmDenueEntidad(models.Model):
    _name = "crm.denue.entidad"
    _description = "Entidad Federativa (código INEGI)"
    _order = "code"

    code = fields.Char(string="Código INEGI", required=True, index=True, size=2)
    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)
