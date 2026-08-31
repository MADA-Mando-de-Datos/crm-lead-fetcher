from odoo import api, fields, models


class CrmDenueSector(models.Model):
    _name = 'crm.denue.sector'
    _description = 'Sector económico DENUE (SCIAN 2023)'
    _order = 'code'

    code = fields.Char(string='Código SCIAN', required=True, index=True)
    name = fields.Char(string='Nombre del sector', required=True)
    sector_code = fields.Char(string='Código sector (2 dígitos)', index=True,
        help='Código del sector padre en la jerarquía SCIAN')
    sector_name = fields.Char(string='Sector padre',
        help='Nombre del sector de 2 dígitos (ej. Información en medios)')
    description = fields.Text(string='Descripción',
        help='Descripción en lenguaje claro del tipo de negocios que incluye')
    keywords = fields.Char(string='Palabras clave',
        help='Términos de búsqueda separados por comas')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Búsqueda mejorada (Odoo 18): código SCIAN, nombre, sector padre y keywords."""
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        domain = ['|', '|', '|',
                  ('code', operator, name),
                  ('name', operator, name),
                  ('sector_name', operator, name),
                  ('keywords', operator, name)]
        return super().name_search(name='', args=(args or []) + domain, operator=operator, limit=limit)