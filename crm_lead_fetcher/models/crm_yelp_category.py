from odoo import api, fields, models


class CrmYelpCategory(models.Model):
    _name = "crm.yelp.category"
    _description = "Categoría Yelp"
    _order = "name"

    alias = fields.Char(
        string="Alias Yelp",
        required=True,
        index=True,
        help="Identificador de la categoría en Yelp (ej: restaurants, plumbing)",
    )
    name = fields.Char(string="Nombre", required=True, help="Nombre legible de la categoría")
    keywords = fields.Char(string="Palabras clave", help="Términos de búsqueda separados por comas")

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)
        domain = ["|", "|", ("alias", operator, name), ("name", operator, name), ("keywords", operator, name)]
        return super().name_search(name="", args=(args or []) + domain, operator=operator, limit=limit)
