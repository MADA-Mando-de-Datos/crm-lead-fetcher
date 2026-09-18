from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # --- DENUE ---
    denue_token = fields.Char(
        string="Token de la API DENUE",
        config_parameter="crm_lead_fetcher.denue_token",
        help="Obtenga su token gratuito en https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx",
    )
    denue_entidad = fields.Char(
        string="Código de entidad INEGI",
        default="24",
        config_parameter="crm_lead_fetcher.denue_entidad",
        help="Código de 2 dígitos de la entidad federativa. Ej: 09=CDMX, 14=Jalisco, 24=SLP.",
    )
    denue_max_records = fields.Integer(
        string="Máximo de registros por búsqueda",
        default=30000,
        config_parameter="crm_lead_fetcher.denue_max_records",
        help="Máximo de registros que descargará por búsqueda. Más registros = más leads pero más lento.",
    )
    denue_sleep_seconds = fields.Float(
        string="Pausa entre llamadas (segundos)",
        default=2.0,
        config_parameter="crm_lead_fetcher.denue_sleep_seconds",
        help="Pausa en segundos entre cada petición al API. Recomendado 1-3 para evitar límites de tasa.",
    )

    # --- YELP ---
    yelp_api_key = fields.Char(
        string="API Key de Yelp",
        config_parameter="crm_lead_fetcher.yelp_api_key",
        help="Obtenga su API Key gratuita en https://www.yelp.com/developers/v3/manage_app",
    )
    yelp_location = fields.Char(
        string="Ubicación por defecto",
        default="San Luis Potosí, México",
        config_parameter="crm_lead_fetcher.yelp_location",
        help='Ciudad o dirección para búsquedas Yelp. Ej: "CDMX", "Monterrey, Nuevo León".',
    )
    yelp_max_results = fields.Integer(
        string="Máximo de resultados Yelp",
        default=240,
        config_parameter="crm_lead_fetcher.yelp_max_results",
        help="Máximo de resultados por búsqueda (máximo 240 por límite de Yelp).",
    )

    # --- GOOGLE PLACES ---
    google_places_api_key = fields.Char(
        string="API Key de Google Places",
        config_parameter="crm_lead_fetcher.google_places_api_key",
        help="Obtenga su API Key en https://console.cloud.google.com/google/maps-apis",
    )
    google_location = fields.Char(
        string="Ubicación por defecto Google",
        default="San Luis Potosí, México",
        config_parameter="crm_lead_fetcher.google_location",
        help="Ciudad o dirección por defecto para búsquedas Google Places.",
    )
    google_max_results = fields.Integer(
        string="Máximo de resultados Google",
        default=60,
        config_parameter="crm_lead_fetcher.google_max_results",
        help="Máximo de resultados por búsqueda (máximo 60 por límites de Google Text Search).",
    )

    @api.constrains("yelp_max_results")
    def _check_yelp_max_results(self):
        for record in self:
            if record.yelp_max_results and (record.yelp_max_results <= 0 or record.yelp_max_results > 240):
                raise UserError(_("El máximo de resultados para Yelp debe estar entre 1 y 240."))

    @api.constrains("google_max_results")
    def _check_google_max_results(self):
        for record in self:
            if record.google_max_results and (record.google_max_results <= 0 or record.google_max_results > 60):
                raise UserError(_("El máximo de resultados para Google Places debe estar entre 1 y 60."))

    def _test_source_connection(self, source_key):
        """Método unificado para probar conectividad delegando a la fuente correspondiente."""
        self.ensure_one()
        source = self.env["lead.source.registry"].get_source(source_key)
        success, message = source.test_connection(config=self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Conexión exitosa") if success else _("Fallo de conexión"),
                "message": message,
                "type": "success" if success else "danger",
                "sticky": not success,
            },
        }

    def action_test_denue_connection(self):
        return self._test_source_connection("denue")

    def action_test_yelp_connection(self):
        return self._test_source_connection("yelp")

    def action_test_google_connection(self):
        return self._test_source_connection("google")

    def action_open_denue_token_page(self):
        return {
            "type": "ir.actions.act_url",
            "url": "https://www.inegi.org.mx/app/api/denue/v1/tokenVerify.aspx",
            "target": "new",
        }

    def action_open_yelp_developer_page(self):
        return {
            "type": "ir.actions.act_url",
            "url": "https://www.yelp.com/developers/v3/manage_app",
            "target": "new",
        }

    def action_open_google_developer_page(self):
        return {
            "type": "ir.actions.act_url",
            "url": "https://console.cloud.google.com/google/maps-apis",
            "target": "new",
        }
