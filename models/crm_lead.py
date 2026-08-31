from odoo import _, fields, models
from odoo.exceptions import UserError


class Lead(models.Model):
    _inherit = 'crm.lead'

    external_id = fields.Char(string='ID Externo', index=True,
        help='ID del registro en la fuente de datos original (DENUE, Yelp, Google Places)')
    lead_request_id = fields.Many2one('crm.lead.request', string='Solicitud de Minado', index='btree_not_null')
    source_key = fields.Selection(
        related='lead_request_id.source_key',
        store=True,
        string='Fuente de Datos',
        help='Origen de minado del lead (DENUE, Yelp, Google Places)'
    )
    source_rating = fields.Float(string='Calificación del Negocio',
        help='Calificación promedio del negocio en la fuente de origen')
    source_reviews = fields.Integer(string='Número de Reseñas',
        help='Cantidad de reseñas del negocio en la fuente de origen')
    source_price_level = fields.Selection([
        ('0', 'Gratis'),
        ('1', 'Económico'),
        ('2', 'Moderado'),
        ('3', 'Caro'),
        ('4', 'Muy caro'),
    ], string='Nivel de Precio', help='Nivel de precio reportado por la fuente')
    # Precio en moneda local (Yelp): 1-4
    yelp_price = fields.Integer(string='Precio (Yelp)', help='Nivel de precio Yelp (1-4)')
    latitude = fields.Float(string='Latitud', digits=(9, 6), help='Latitud del negocio')
    longitude = fields.Float(string='Longitud', digits=(9, 6), help='Longitud del negocio')

    def action_enrich_email(self):
        """Dispara el proceso de enriquecimiento de email para este lead.
        Utiliza el modelo *lead.email.enricher* que busca en la página web
        (y rutas de contacto comunes) y asigna el primer email hallado.
        """
        self.ensure_one()
        if not self.website:
            raise UserError(_('El lead no tiene sitio web para intentar el enriquecimiento.'))
        enricher = self.env['lead.email.enricher']
        email = enricher.enrich_url(self.website)
        if email:
            self.email_from = email
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Enriquecimiento completado'),
                    'message': _('Se estableció el email: %s', email),
                    'type': 'success',
                },
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin resultados'),
                    'message': _('No se encontró un email en la web del lead.'),
                    'type': 'warning',
                },
            }

