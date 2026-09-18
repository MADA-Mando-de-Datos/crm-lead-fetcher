import ipaddress
import logging
import re
import socket
import urllib.parse
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LeadEmailEnricher(models.AbstractModel):
    """Servicio seguro de extracción de correos electrónicos y descubrimiento web.
    Valida contra SSRF (bloquea IPs locales y privadas) y aplica límites estrictos de timeout.
    """

    _name = "lead.email.enricher"
    _description = "Enriquecimiento y Descubrimiento Web para Leads"

    EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB máximo para evitar descargas pesadas
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT = 7

    # Dominios de directorios o plataformas que deben descartarse al buscar la web oficial
    DISCOVERY_EXCLUDE_DOMAINS = (
        "duckduckgo.com",
        "bing.com",
        "civitatis.com",
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "youtube.com",
        "yelp.com",
        "yelp.com.mx",
        "tripadvisor.com",
        "tripadvisor.com.mx",
        "tripadvisor.es",
        "restaurantguru.com",
        "paginasamarillas.com",
        "seccionamarilla.com.mx",
        "directoriodenotarios.com.mx",
        "serviciosnotariales.org.mx",
        "inegi.org.mx",
        "google.com",
        "maps.google.com",
        "wikipedia.org",
        "mercadolibre.com.mx",
        "amazon.com.mx",
        "foursquare.com",
        "cylex.mx",
        "infoisinfo.com.mx",
        "guiaempresas.com.mx",
        "cybo.com",
        "infobel.mx",
        "tufieston.com",
        "directmap.info",
        "cheapflights.com",
        "sierratours.com.mx",
        "dnb.com",
        "dunsguide.com",
        "mexicoo.mx",
        "pymes.org.mx",
        "mexicopymes.com",
        "directorioempresarialmexico.com",
        "directoriodenegocios.net",
        "infomaquila.com",
        "cataloxy-mx.com",
        "municipiodata.com",
        "comercioempresa.com",
        "encuentren.me",
        "bufetesjuridicos.com",
        "worldplaces.me",
        "directorio.gratis",
        "notariacercademi.com.mx",
        "notariasoficiales.com.mx",
        "busconotario.com.mx",
    )

    CONTACT_KEYWORDS = (
        "contacto",
        "contact",
        "atencion",
        "nosotros",
        "about",
        "acerca",
        "soporte",
        "support",
        "escribenos",
        "ubicacion",
    )

    DISCARD_EMAIL_DOMAINS = (
        "wixpress.com",
        "example.com",
        "domain.com",
        "sentry.io",
        "github.com",
        "google.com",
        "facebook.com",
        "twitter.com",
        "instagram.com",
        "wordpress.org",
        "gravatar.com",
    )

    DISCARD_EMAIL_EXTENSIONS = (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".bmp",
        ".tiff",
        ".ico",
        ".css",
        ".js",
        ".woff",
        ".woff2",
        ".ttf",
    )

    @api.model
    def _is_safe_url(self, url):
        """Verifica que la URL no apunte a hosts locales, privados o reservados (Anti-SSRF)."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            hostname = parsed.hostname
            if not hostname:
                return False

            # Resolver hostname a IP
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip_str = info[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_reserved
                    or ip_obj.is_multicast
                ):
                    _logger.warning("LeadEnricher: Bloqueada URL con IP privada/local: %s (%s)", url, ip_str)
                    return False
            return True
        except Exception as e:
            _logger.debug("LeadEnricher: Error validando seguridad de URL %s: %s", url, e)
            return False

    @api.model
    def _fetch(self, url):
        """Obtiene el contenido HTML de *url* de forma segura con timeout estricto."""
        if not self._is_safe_url(url):
            return None

        try:
            import requests

            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MADA-Lead-Enricher/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                }
            )
            resp = session.get(
                url,
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
                allow_redirects=True,
                stream=True,
            )
            if resp.status_code != 200:
                return None

            content_type = resp.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type:
                return None

            content = resp.raw.read(self.MAX_RESPONSE_BYTES, decode_content=True)
            return content.decode(resp.encoding or "utf-8", errors="ignore")
        except Exception as e:
            _logger.debug("LeadEnricher: error fetching %s -> %s", url, e)
            return None

    @api.model
    def _is_valid_email(self, email):
        """Valida higiene de correo electrónico descartando falsos positivos."""
        if not email or not isinstance(email, str):
            return False
        clean = email.strip().lower()
        if any(clean.endswith(ext) for ext in self.DISCARD_EMAIL_EXTENSIONS):
            return False
        if any(dummy in clean for dummy in self.DISCARD_EMAIL_DOMAINS):
            return False
        parts = clean.split("@")
        if len(parts) != 2:
            return False
        local_part, domain_part = parts
        return not (not local_part or not domain_part or "." not in domain_part)

    @api.model
    def _extract_email(self, html):
        """Busca correos válidos en texto plano y etiquetas HTML."""
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # 1. Prioridad: Enlaces explicitos <a href="mailto:...">
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().startswith("mailto:"):
                candidate = href[7:].split("?")[0].strip()
                if self._is_valid_email(candidate):
                    return candidate

        # 2. Regex sobre el texto y contenido
        matches = re.findall(self.EMAIL_REGEX, html, re.IGNORECASE)
        for email in matches:
            if self._is_valid_email(email):
                return email
        return None

    @api.model
    def _extract_social_and_whatsapp(self, html):
        """Extrae enlaces de WhatsApp y redes sociales principales."""
        channels = {}
        if not html:
            return channels

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            href_lower = href.lower()
            if "wa.me/" in href_lower or "api.whatsapp.com/send" in href_lower:
                if "whatsapp" not in channels:
                    channels["whatsapp"] = href
            elif "facebook.com/" in href_lower and not any(p in href_lower for p in ("sharer", "share.php")):
                if "facebook" not in channels:
                    channels["facebook"] = href
            elif "instagram.com/" in href_lower:
                if "instagram" not in channels:
                    channels["instagram"] = href
            elif "linkedin.com/company/" in href_lower and "linkedin" not in channels:
                channels["linkedin"] = href
        return channels

    @api.model
    def _find_contact_links(self, base_url, html):
        """Encuentra enlaces de contacto dinámicamente en el DOM de la página principal."""
        found_urls = []
        if not html:
            return found_urls

        try:
            soup = BeautifulSoup(html, "html.parser")
            base_parsed = urlparse(base_url)
            base_netloc = base_parsed.netloc.lower()

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = (a.get_text() or "").strip().lower()
                href.lower()

                # Ignorar anclas internas o scripts
                if href.startswith(("#", "javascript:", "tel:", "mailto:")):
                    continue

                full_url = urljoin(base_url, href)
                parsed_full = urlparse(full_url)

                # Mantenerse dentro del mismo dominio
                if parsed_full.netloc.lower() != base_netloc:
                    continue

                path_lower = parsed_full.path.lower()
                # Coincidencia con palabras clave en texto o ruta
                is_contact_link = any(kw in path_lower for kw in self.CONTACT_KEYWORDS) or any(
                    kw in text for kw in self.CONTACT_KEYWORDS
                )

                if is_contact_link and full_url not in found_urls and full_url != base_url:
                    found_urls.append(full_url)
                    if len(found_urls) >= 4:
                        break
        except Exception as e:
            _logger.debug("LeadEnricher: error parsing contact links: %s", e)

        return found_urls

    @api.model
    def enrich_url(self, base_url):
        """Intenta extraer un email a partir de *base_url* y rutas dinámicas de contacto."""
        if not base_url:
            raise UserError(_("URL vacía"))
        base_url = base_url.strip()
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        base_url = base_url.rstrip("/")

        # 1. Consultar portada
        home_html = self._fetch(base_url)
        if home_html:
            email = self._extract_email(home_html)
            if email:
                return email

        # 2. Descubrimiento dinámico de enlaces de contacto en el DOM
        dynamic_contact_urls = self._find_contact_links(base_url, home_html) if home_html else []

        # 3. Candidatos combinados (dinámicos primero, luego rutas fijas tradicionales)
        fixed_fallback = [
            f"{base_url}/contacto",
            f"{base_url}/contact",
            f"{base_url}/nosotros",
            f"{base_url}/about",
        ]
        candidates = dynamic_contact_urls + [u for u in fixed_fallback if u not in dynamic_contact_urls]

        for url in candidates[:5]:
            html = self._fetch(url)
            email = self._extract_email(html)
            if email:
                return email
        return None

    @api.model
    def discover_website_by_query(self, name, location=None):
        """Busca de forma orgánica en la web la URL oficial de un negocio según su nombre y ubicación.
        Descarta directorios y plataformas masivas mediante filtrado negativo.
        """
        if not name or not name.strip():
            return None

        clean_name = name.strip()
        clean_loc = (location or "").strip()

        # Estrategia 1: Búsqueda exacta entre comillas
        # Estrategia 2: Búsqueda natural sin comillas (fallback)
        queries = []
        if clean_loc:
            queries.append(f'"{clean_name}" "{clean_loc}"')
            queries.append(f"{clean_name} {clean_loc}")
        else:
            queries.append(f'"{clean_name}"')
            queries.append(clean_name)

        for query in queries:
            try:
                data = urllib.parse.urlencode({"q": query}).encode("utf-8")
                req = urllib.request.Request(
                    "https://html.duckduckgo.com/html/",
                    data=data,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html_resp = resp.read().decode("utf-8", errors="ignore")

                soup = BeautifulSoup(html_resp, "html.parser")
                for a in soup.find_all("a", class_="result__url"):
                    href = (a.get("href") or "").strip()
                    if not href.startswith(("http://", "https://")):
                        continue
                    parsed = urlparse(href)
                    domain = (parsed.hostname or "").lower()

                    # Ignorar dominios excluidos (directorios, redes sociales genéricas)
                    if any(excluded in domain for excluded in self.DISCOVERY_EXCLUDE_DOMAINS):
                        continue

                    if self._is_safe_url(href):
                        # Retornar URL base limpia del sitio web oficial
                        return f"{parsed.scheme}://{parsed.netloc}"

            except Exception as e:
                _logger.debug('LeadEnricher: Error en descubrimiento web orgánico para "%s": %s', query, e)

        return None
