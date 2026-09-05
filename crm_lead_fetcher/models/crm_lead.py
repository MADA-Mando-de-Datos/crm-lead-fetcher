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
        Si no tiene sitio web, intenta descubrirlo orgánicamente primero.
        """
        self.ensure_one()
        enricher = self.env['lead.email.enricher']

        # Si no tiene website o la web es solo la ficha de Yelp/directorio, intentar descubrir la web real
        website_discovered = False
        is_directory_link = bool(self.website and any(d in self.website.lower() for d in enricher.DISCOVERY_EXCLUDE_DOMAINS))
        if (not self.website or is_directory_link) and self.name:
            location = self.city or (self.state_id.name if self.state_id else '')
            discovered_url = enricher.discover_website_by_query(self.name, location)
            if discovered_url:
                self.website = discovered_url
                website_discovered = True

        if not self.website:
            raise UserError(_('El lead no tiene sitio web y no se pudo descubrir automáticamente.'))

        email = enricher.enrich_url(self.website)
        if email:
            self.email_from = email
            msg = _('Se estableció el email: %s', email)
            if website_discovered:
                msg = _('Se descubrió la web (%s) y se estableció el email: %s', self.website, email)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Enriquecimiento completado'),
                    'message': msg,
                    'type': 'success',
                },
            }
        else:
            msg = _('No se encontró un email en la web del lead.')
            if website_discovered:
                msg = _('Se descubrió la web (%s), pero no se encontró un email de contacto.', self.website)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin resultados de email'),
                    'message': msg,
                    'type': 'warning',
                },
            }

    def action_enrich_email_batch(self):
        """Procesa el enriquecimiento de email y descubrimiento web en lote para los leads seleccionados."""
        enricher = self.env['lead.email.enricher']
        enriched_count = 0
        discovered_web_count = 0

        for lead in self:
            # 1. Descubrir web si no tiene o si solo apunta a un directorio/Yelp
            is_dir_link = bool(lead.website and any(d in lead.website.lower() for d in enricher.DISCOVERY_EXCLUDE_DOMAINS))
            if (not lead.website or is_dir_link) and lead.name:
                location = lead.city or (lead.state_id.name if lead.state_id else '')
                discovered_url = enricher.discover_website_by_query(lead.name, location)
                if discovered_url:
                    lead.website = discovered_url
                    discovered_web_count += 1

            # 2. Si tiene web y no tiene email (o para actualizar), intentar enriquecer
            if lead.website and not lead.email_from and not any(d in lead.website.lower() for d in enricher.DISCOVERY_EXCLUDE_DOMAINS):
                found_email = enricher.enrich_url(lead.website)
                if found_email:
                    lead.email_from = found_email
                    enriched_count += 1

        title = _('Enriquecimiento en lote finalizado')
        msg = _(
            'Proceso completado para %d lead(s): %d email(s) asignado(s), %d sitio(s) web descubierto(s).',
            len(self),
            enriched_count,
            discovered_web_count,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': msg,
                'type': 'success' if (enriched_count > 0 or discovered_web_count > 0) else 'info',
            },
        }


