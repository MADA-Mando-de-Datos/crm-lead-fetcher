import logging

_logger = logging.getLogger(__name__)


def uninstall_hook(env):
    """Limpia parámetros y metadatos huérfanos al desinstalar el módulo.

    Sigue el patrón de Odoo Base y OCA para evitar que queden campos residuales
    en res.config.settings o registros desvinculados que provoquen errores RPC.
    """
    _logger.info("Ejecutando uninstall_hook de crm_lead_fetcher...")

    params = [
        "crm_lead_fetcher.denue_token",
        "crm_lead_fetcher.denue_entidad",
        "crm_lead_fetcher.denue_max_records",
        "crm_lead_fetcher.denue_sleep_seconds",
        "crm_lead_fetcher.yelp_api_key",
        "crm_lead_fetcher.yelp_location",
        "crm_lead_fetcher.yelp_max_results",
        "crm_lead_fetcher.google_places_api_key",
        "crm_lead_fetcher.google_location",
        "crm_lead_fetcher.google_max_results",
    ]
    env["ir.config_parameter"].sudo().search([("key", "in", params)]).unlink()

    _logger.info("uninstall_hook de crm_lead_fetcher completado exitosamente.")
