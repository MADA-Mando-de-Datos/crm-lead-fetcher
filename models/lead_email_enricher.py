from odoo import _, api, models
import re
# requests will be imported lazily within _fetch
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LeadEmailEnricher(models.AbstractModel):
    """Servicio sencillo de extracción de correos electrónicos a partir de la URL del sitio web.
    Busca en la página principal y en rutas típicas de contacto ("/contact", "/contacto", "/about", "/nosotros").
    Retorna el primer email encontrado o ``None``.
    """

    _name = 'lead.email.enricher'
    _description = 'Enriquecimiento de Email a partir de la URL del Lead'

    EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    @api.model
    def _fetch(self, url):
        """Obtiene el HTML de *url* con timeout y manejo de errores.
        Si la respuesta no es 200, devuelve ``None``.
        """
        try:
            import requests
            resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (crm-lead-enricher)'})
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            _logger.warning('LeadEnricher: error fetching %s -> %s', url, e)
            return None

    @api.model
    def _extract_email(self, html):
        """Busca el primer email en el HTML usando una expresión regular.
        Devuelve ``None`` si no encuentra coincidencias.
        """
        if not html:
            return None
        match = re.search(self.EMAIL_REGEX, html, re.IGNORECASE)
        return match.group(0) if match else None

    @api.model
    def enrich_url(self, base_url):
        """Intenta extrair un email a partir de *base_url* y rutas comunes.
        Devuelve el email como ``str`` o ``None``.
        """
        if not base_url:
            raise UserError(_('URL vacía'))
        # Normalizar la URL (sin slash final)
        base_url = base_url.strip().rstrip('/')
        candidates = [
            base_url,
            f"{base_url}/contact",
            f"{base_url}/contacto",
            f"{base_url}/about",
            f"{base_url}/nosotros",
        ]
        for url in candidates:
            html = self._fetch(url)
            email = self._extract_email(html)
            if email:
                return email
        return None
