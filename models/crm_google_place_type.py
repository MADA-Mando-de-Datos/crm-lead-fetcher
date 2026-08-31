from odoo import api, fields, models


class CrmGooglePlaceType(models.Model):
    _name = 'crm.google.place.type'
    _description = 'Tipo de establecimiento Google Places'
    _order = 'name asc'

    name = fields.Char(string='Tipo / Giro', required=True)
    code = fields.Char(string='Código Google', required=True, index=True,
                       help='Identificador oficial de Google Places API (ej: restaurant, lawyer, accounting)')
    keywords = fields.Char(string='Palabras clave',
                           help='Términos relacionados separados por coma')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'El código del tipo de Google ya existe.')
    ]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        domain = ['|', '|',
                  ('code', operator, name),
                  ('name', operator, name),
                  ('keywords', operator, name)]
        return super().name_search(name='', args=(args or []) + domain, operator=operator, limit=limit)

