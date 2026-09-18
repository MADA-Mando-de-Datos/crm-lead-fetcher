from odoo import _, api, models
from odoo.exceptions import UserError

from .lead_source import ESTRATO_LABELS

MAX_DENUE_GEO_DISTANCE = 5000


class LeadSourceDenue(models.AbstractModel):
    """Implementación DENUE (INEGI) de lead source."""

    _name = "lead.source.denue"
    _inherit = "lead.source"
    _description = "DENUE (INEGI) - Directorio Nacional de Unidades Económicas"

    @api.model
    def _get_api(self):
        return self.env["denue.api"]

    @api.model
    def _get_denue_token(self):
        return (self.env["ir.config_parameter"].sudo().get_param("crm_lead_fetcher.denue_token", "")).strip()

    @api.model
    def _get_max_records(self):
        return int(self.env["ir.config_parameter"].sudo().get_param("crm_lead_fetcher.denue_max_records", "30000"))

    @api.model
    def validate_filters(self, wizard):
        """Valida las reglas específicas de búsqueda para DENUE (INEGI)."""
        if not wizard.entidad_ids:
            raise UserError(_("Seleccione al menos una entidad federativa."))
        st = wizard.search_type
        if st == "by_state" and not wizard.sector_ids:
            raise UserError(_('En búsqueda "Todo el estado" debe seleccionar al menos un sector SCIAN.'))
        if st == "by_activity_state" and not (wizard.actividad or "").strip():
            raise UserError(_("Capture la actividad o palabra clave a buscar."))
        if st == "by_name_state" and not (wizard.nombre_busqueda or "").strip():
            raise UserError(_("Capture el nombre del establecimiento a buscar."))

    @api.model
    def build_filters(self, wizard):
        """Construye los parámetros para el cliente DENUE API."""
        return {
            "entidad_ids": [e.code for e in wizard.entidad_ids],
            "search_type": wizard.search_type,
            "sectores": [s.code for s in wizard.sector_ids],
            "actividad": (wizard.actividad or "").strip(),
            "nombre": (wizard.nombre_busqueda or "").strip(),
            "estrato_min": wizard.estrato_min or None,
            "estrato_max": wizard.estrato_max or None,
        }

    @api.model
    def search(self, filters, max_records):
        entidad_ids = filters.get("entidad_ids") or []
        if not entidad_ids:
            raise ValueError(_("Debe seleccionar al menos una entidad"))

        search_type = filters.get("search_type", "by_state")
        all_matches = []

        for entidad in entidad_ids:
            for gen in self._generators_for(search_type, filters, entidad, max_records):
                for record in gen:
                    all_matches.append(record)
                    if len(all_matches) >= max_records:
                        return all_matches

        return all_matches[:max_records]

    @api.model
    def _generators_for(self, search_type, filters, entidad, max_records):
        api = self._get_api()
        if search_type == "by_state":
            codes = [str(c) for c in (filters.get("sectores") or [])]
            if codes:
                # El gateway de INEGI aborta la conexión (HTTP 000) cuando se
                # consulta BuscarAreaAct por sub-sector (código de 3 dígitos).
                # Para evitar ese fallo se consulta por sector de 2 dígitos
                # (padre) y el sub-sector se filtra en cliente (post_filter).
                padres = sorted({code[:2] for code in codes})
                return [api.search_by_area_act(entidad, p, max_records) for p in padres]
            return [api.search_by_state(entidad, max_records)]
        if search_type == "by_activity_state":
            actividad = filters.get("actividad", "")
            if not actividad:
                return []
            return [api.search_by_activity_and_state(actividad, entidad, max_records)]
        if search_type == "by_name_state":
            nombre = filters.get("nombre", "")
            if not nombre:
                return []
            return [api.search_by_name_and_state(nombre, entidad, max_records)]
        return []

    @api.model
    def test_connection(self, config=None):
        token = (
            (config.denue_token if config and hasattr(config, "denue_token") else None) or self._get_denue_token() or ""
        ).strip()
        entidad = ((config.denue_entidad if config and hasattr(config, "denue_entidad") else None) or "24").strip()
        if not token:
            return False, _("Configure el Token de DENUE primero.")
        url = f"https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarEntidad/todos/{entidad}/1/1/{token}"
        import requests

        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (crm-lead-mining)"})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return True, _("Conexión exitosa. DENUE respondió con %d registro(s) de prueba.", len(data))
        except Exception as e:
            err_msg = str(e)
            if token and token in err_msg:
                err_msg = err_msg.replace(token, "[TOKEN_PROTEGIDO]")
            return False, _("Error de conexión con DENUE: %s", err_msg)

    @api.model
    def get_available_filters(self):
        return [
            {
                "field": "entidad_ids",
                "label": "Entidades",
                "type": "many2many",
                "model": "crm.denue.entidad",
                "required": True,
                "help": "Estados a buscar (códigos INEGI)",
            },
            {
                "field": "search_type",
                "label": "Tipo de búsqueda",
                "type": "selection",
                "selection": [
                    ("by_state", "Todo el estado"),
                    ("by_activity_state", "Por actividad + estado"),
                    ("by_name_state", "Por nombre + estado"),
                ],
                "required": True,
                "default": "by_state",
            },
            {"field": "actividad", "label": "Actividad / Palabra clave", "type": "char"},
            {"field": "nombre_busqueda", "label": "Nombre del establecimiento", "type": "char"},
            {"field": "sector_ids", "label": "Sectores SCIAN", "type": "many2many", "model": "crm.denue.sector"},
            {
                "field": "estrato_min",
                "label": "Estrato mínimo",
                "type": "selection",
                "selection": [(i, ESTRATO_LABELS[i]) for i in range(1, 8)],
            },
            {
                "field": "estrato_max",
                "label": "Estrato máximo",
                "type": "selection",
                "selection": [(i, ESTRATO_LABELS[i]) for i in range(1, 8)],
            },
        ]

    @api.model
    def get_external_id(self, record):
        return str(record.get("Id") or "").strip()

    @api.model
    def get_automatic_tag_names(self, record):
        """Devuelve nombres de etiquetas de sector SCIAN para un registro DENUE."""
        code = str(record.get("SUBSECTOR_ACTIVIDAD_ID") or record.get("SECTOR_ACTIVIDAD_ID") or "").strip()
        if not code:
            return []
        Sector = self.env["crm.denue.sector"]
        sector = Sector.search([("code", "=", code)], limit=1)
        if not sector and len(code) >= 3:
            sector = Sector.search([("code", "=", code[:2])], limit=1)
        if not sector:
            return []
        label = sector.sector_name or sector.name
        return [f"{sector.code} {label}"[:40]]

    @api.model
    def record_to_lead_vals(self, record, lead_type, team_id, user_id, tag_ids, request_id):
        return self.env["denue.lead.helpers"].lead_vals(record, lead_type, team_id, user_id, tag_ids, request_id)

    @api.model
    def post_filter(self, records, wizard):
        """Aplica filtros client-side de DENUE: estrato y subsector."""
        filtered = list(records)
        estrato_min = getattr(wizard, "estrato_min", None)
        estrato_max = getattr(wizard, "estrato_max", None)
        helpers = self.env["denue.lead.helpers"]

        def _get_estrato_val(r):
            raw = r.get("estrato") or r.get("Estrato")
            if isinstance(raw, int):
                return raw
            if isinstance(raw, str):
                if raw.isdigit():
                    return int(raw)
                return helpers.estrato_to_int(raw)
            return 0

        if estrato_min:
            emin = int(estrato_min)
            filtered = [r for r in filtered if _get_estrato_val(r) >= emin]
        if estrato_max:
            emax = int(estrato_max)
            filtered = [r for r in filtered if _get_estrato_val(r) <= emax]

        # Filtrado por sub-sector (código de 3 dígitos) en cliente: el gateway
        # de INEGI aborta BuscarAreaAct por sub-sector, así que se consulta el
        # sector padre (2 dígitos) y se acota aquí usando SUBSECTOR_ACTIVIDAD_ID.
        subs = {str(s.code) for s in wizard.sector_ids if len(str(s.code)) >= 3}
        if subs:
            full_sectors = {str(s.code) for s in wizard.sector_ids if len(str(s.code)) == 2}

            def _keep_sub(r):
                sub = str(r.get("SUBSECTOR_ACTIVIDAD_ID") or "")
                sec = str(r.get("SECTOR_ACTIVIDAD_ID") or "")
                return sub in subs or sec in full_sectors

            filtered = [r for r in filtered if _keep_sub(r)]

        return filtered

    @api.model
    def get_scan_cap(self):
        return self._get_max_records()
