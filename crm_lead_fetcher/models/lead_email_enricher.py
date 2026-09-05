import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LeadEmailEnricher(models.AbstractModel):
    """Servicio seguro de extracción de correos electrónicos a partir de la URL del sitio web.
    Valida contra SSRF (bloquea IPs locales y privadas) y aplica límites estrictos de timeout.
    """

    _name = 'lead.email.enricher'
    _description = 'Enriquecimiento de Email a partir de la URL del Lead'

    EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB máximo para evitar descargas pesadas
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT = 7

    @api.model
    def _is_safe_url(self, url):
        """Verifica que la URL no apunte a hosts locales, privados o reservados (Anti-SSRF)."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False
            hostname = parsed.hostname
            if not hostname:
                return False

            # Resolver hostname a IP
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip_str = info[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (ip_obj.is_private or ip_obj.is_loopback or
                        ip_obj.is_link_local or ip_obj.is_reserved or
                        ip_obj.is_multicast):
                    _logger.warning('LeadEnricher: Bloqueada URL con IP privada/local: %s (%s)', url, ip_str)
                    return False
            return True
        except Exception as e:
            _logger.debug('LeadEnricher: Error validando seguridad de URL %s: %s', url, e)
            return False

    @api.model
    def _fetch(self, url):
        """Obtiene el contenido HTML de *url* de forma segura con timeout estricto."""
        if not self._is_safe_url(url):
            return None

        try:
            import requests
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MADA-Lead-Enricher/1.0',
                'Accept': 'text/html,application/xhtml+xml',
            })
            resp = session.get(
                url,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
                allow_redirects=True,
                stream=True,
            )
            if resp.status_code != 200:
                return None

            content_type = resp.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                return None

            # Leer hasta MAX_RESPONSE_BYTES
            content = resp.raw.read(self.MAX_RESPONSE_BYTES, decode_content=True)
            return content.decode(resp.encoding or 'utf-8', errors='ignore')
        except Exception as e:
            _logger.debug('LeadEnricher: error fetching %s -> %s', url, e)
            return None

    @api.model
    def _extract_email(self, html):
        """Busca correos electrónicos válidos en el HTML descartando falsos positivos comunes."""
        if not html:
            return None
        matches = re.findall(self.EMAIL_REGEX, html, re.IGNORECASE)
        for email in matches:
            email_lower = email.lower()
            # Descartar extensiones de imagen o falsos positivos comunes de código
            if not any(email_lower.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                if not any(dummy in email_lower for dummy in ('wixpress.com', 'example.com', 'domain.com', 'sentry.io')):
                    return email
        return None

    @api.model
    def enrich_url(self, base_url):
        """Intenta extraer un email a partir de *base_url* y rutas comunes."""
        if not base_url:
            raise UserError(_('URL vacía'))
        base_url = base_url.strip()
        if not base_url.startswith(('http://', 'https://')):
            base_url = f'https://{base_url}'
        base_url = base_url.rstrip('/')

        candidates = [
            base_url,
            f"{base_url}/contacto",
            f"{base_url}/contact",
            f"{base_url}/nosotros",
            f"{base_url}/about",
        ]
        for url in candidates:
            html = self._fetch(url)
            email = self._extract_email(html)
            if email:
                return email
        return None
