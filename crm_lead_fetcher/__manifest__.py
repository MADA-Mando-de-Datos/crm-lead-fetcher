{
    'name': 'Lead Mining CRM (DENUE + Yelp + Google)',
    'version': '18.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Generate CRM leads from multiple sources: DENUE (INEGI), Yelp and Google Places',
    'description': """
B2B lead mining module that generates CRM leads from multiple data sources.

Available sources:
- DENUE (INEGI): Free directory of Mexican business establishments
- Yelp Fusion API: Business directory with reviews and ratings
- Google Places API: Global directory of businesses and services (Google Maps)

Features:
- Extensible architecture to add new sources
- Wizard with source-specific filters
- Advanced filters by sector, type, size, location, rating, price
- Automatic tagging by sector/category/type
- Deduplication by external ID (Place ID, Yelp ID, DENUE ID)
- Cross-source deduplication by business fingerprint (name + location / phone)
- Automatic assignment to sales team and salesperson
- Website-based email enrichment
- CSV export of mined leads
- 100% Spanish interface
    """,
    'license': 'LGPL-3',
    'author': 'MADA | Mando de Datos',
    'website': 'https://madamexico.me',
    'support': 'hola@madamexico.me',
    'depends': ['base', 'crm'],
    'external_dependencies': {
        'python': ['beautifulsoup4'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/crm_denue_sector_data.xml',
        'data/crm_denue_entidad_data.xml',
        'data/crm_yelp_category_data.xml',
        'data/crm_google_place_type_data.xml',
        'views/crm_lead_actions.xml',
        'views/crm_lead_request_views.xml',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}
