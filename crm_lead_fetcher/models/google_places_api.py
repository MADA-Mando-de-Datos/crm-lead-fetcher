import time

from odoo import _, api, models

from ..exceptions import (
    LeadSourceAuthError,
    LeadSourceConnectionError,
    LeadSourceDataError,
    LeadSourceQuotaError,
)


class GooglePlacesAPI(models.AbstractModel):
    _name = "google.places.api"
    _description = "Cliente API Google Places"

    MAX_RETRIES = 3
    RETRY_BACKOFF = 2
    PAGE_SIZE = 20
    MAX_RESULTS_LIMIT = 60

    @api.model
    def _api_key(self):
        return (self.env["ir.config_parameter"].sudo().get_param("crm_lead_fetcher.google_places_api_key", "")).strip()

    @api.model
    def _location(self):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("crm_lead_fetcher.google_location", "San Luis Potosí, México")
        ).strip()

    @api.model
    def _max_results(self):
        val = self.env["ir.config_parameter"].sudo().get_param("crm_lead_fetcher.google_max_results", "60")
        try:
            return min(int(val or 60), self.MAX_RESULTS_LIMIT)
        except Exception:
            return self.MAX_RESULTS_LIMIT

    @api.model
    def _get(self, url, params=None):
        """GET con reintentos y validación de códigos de error de Google Places."""
        import requests

        api_key = self._api_key()
        if not api_key:
            raise LeadSourceAuthError(_("Configure la API Key de Google Places en Ajustes > CRM > Minado de Leads."))

        params = params or {}
        params["key"] = api_key
        params.setdefault("language", "es")

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.get(url, params=params, timeout=25)
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "OK")

                if status == "OK":
                    return data
                elif status == "ZERO_RESULTS":
                    return {"results": [], "status": status}
                elif status == "OVER_QUERY_LIMIT":
                    raise LeadSourceQuotaError(
                        _(
                            "Límite de cuota excedido en Google Places API. Verifique su cuota o facturación en Google Cloud Console."
                        )
                    )
                elif status == "REQUEST_DENIED":
                    err_msg = data.get("error_message") or _(
                        "Petición rechazada por Google. Verifique que la API Places esté habilitada y la clave sea válida."
                    )
                    raise LeadSourceAuthError(_("Error de autorización en Google Places API: %s", err_msg))
                elif status == "INVALID_REQUEST":
                    err_msg = data.get("error_message") or _("Parámetros de búsqueda inválidos.")
                    raise LeadSourceDataError(_("Petición inválida a Google Places: %s", err_msg))
                else:
                    return data
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as err:
                last_error = err
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF * (attempt + 1))
                continue
            except (LeadSourceQuotaError, LeadSourceAuthError, LeadSourceDataError):
                raise
            except ValueError as err:
                raise LeadSourceDataError(_("Respuesta no JSON recibida de Google Places API.")) from err
            except requests.exceptions.RequestException as err:
                last_error = err
                break
        raise LeadSourceConnectionError(_("Error de conexión con Google Places API: %s", last_error))

    @api.model
    def get_place_details(self, place_id):
        """Obtiene detalles completos de un lugar (teléfono, sitio web, dirección detallada)."""
        if not place_id:
            return {}
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        fields_list = [
            "place_id",
            "name",
            "formatted_address",
            "formatted_phone_number",
            "international_phone_number",
            "website",
            "url",
            "rating",
            "user_ratings_total",
            "price_level",
            "types",
            "business_status",
            "address_components",
            "geometry",
            "opening_hours",
        ]
        params = {
            "place_id": place_id,
            "fields": ",".join(fields_list),
        }
        data = self._get(url, params)
        return data.get("result", {})

    @api.model
    def search_text(
        self,
        query,
        location=None,
        place_type=None,
        radius=None,
        min_price=None,
        max_price=None,
        page_token=None,
        open_now=None,
    ):
        """Ejecuta una búsqueda Text Search en Google Places API."""
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        full_query = (query or "").strip()
        loc = (location or self._location()).strip()

        if loc and loc.lower() not in full_query.lower():
            if full_query:
                full_query = f"{full_query} en {loc}"
            else:
                full_query = loc

        params = {"query": full_query}

        if place_type:
            params["type"] = place_type
        if radius:
            params["radius"] = min(int(radius), 50000)
        if min_price is not None:
            params["minprice"] = min_price
        if max_price is not None:
            params["maxprice"] = max_price
        if open_now:
            params["opennow"] = "true" if open_now is True else "false"
        if page_token:
            params["pagetoken"] = page_token

        data = self._get(url, params)
        return data.get("results", []), data.get("next_page_token")

    @api.model
    def _merge_places(self, targets, new_places):
        """Agrega lugares evitando duplicados por place_id."""
        existing = {p.get("place_id") for p in targets}
        for place in new_places:
            pid = place.get("place_id")
            if pid and pid not in existing:
                existing.add(pid)
                targets.append(place)
        return targets

    @api.model
    def _paginate_type(
        self,
        query=None,
        location=None,
        place_type=None,
        radius=None,
        min_price=None,
        max_price=None,
        max_results=None,
        fetch_details=True,
        open_now=None,
    ):
        """Pagina resultados para un único tipo de lugar."""
        all_places = []
        next_token = None

        while len(all_places) < max_results:
            if next_token:
                time.sleep(2.0)

            results, next_token = self.search_text(
                query=query,
                location=location,
                place_type=place_type or None,
                radius=radius,
                min_price=min_price,
                max_price=max_price,
                page_token=next_token,
                open_now=open_now,
            )

            if not results:
                break

            for place in results:
                if len(all_places) >= max_results:
                    break
                place_id = place.get("place_id")
                if fetch_details and place_id:
                    try:
                        details = self.get_place_details(place_id)
                        if details:
                            merged = dict(place)
                            merged.update(details)
                            all_places.append(merged)
                            continue
                    except Exception:
                        pass
                all_places.append(place)

            if not next_token:
                break

        return all_places

    @api.model
    def paginate(
        self,
        query=None,
        location=None,
        place_types=None,
        radius=None,
        min_price=None,
        max_price=None,
        max_results=None,
        fetch_details=True,
        open_now=None,
    ):
        """Pagina resultados de Google Places y enriquece con Place Details.

        Soporta múltiples tipos de lugar (se ejecuta una búsqueda por tipo y
        se unifican los resultados, deduplicando por place_id).
        """
        max_results = max_results or self._max_results()
        types = (
            list(place_types)
            if isinstance(place_types, list) and place_types
            else ([place_types] if place_types else [])
        )

        if not types:
            return self._paginate_type(
                query=query,
                location=location,
                place_type=None,
                radius=radius,
                min_price=min_price,
                max_price=max_price,
                max_results=max_results,
                fetch_details=fetch_details,
                open_now=open_now,
            ), 0

        merged = []
        # Distribuir el límite entre tipos para no exceder el total deseado
        per_type = max(1, max_results // len(types))
        for t in types:
            places = self._paginate_type(
                query=query,
                location=location,
                place_type=t,
                radius=radius,
                min_price=min_price,
                max_price=max_price,
                max_results=per_type,
                fetch_details=fetch_details,
                open_now=open_now,
            )
            self._merge_places(merged, places)
            if len(merged) >= max_results:
                break
        return merged, len(merged)
