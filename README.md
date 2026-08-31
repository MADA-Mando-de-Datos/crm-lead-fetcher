# Lead Mining CRM (DENUE + Yelp + Google)

Generate qualified B2B leads directly from your CRM by querying multiple public
business directories. Architecturally pluggable: add new sources easily.

Built for **Odoo 18**. Works on Community Edition.

## Features

- **Three pluggable sources:**
  - **DENUE (INEGI):** official free directory of Mexican business establishments.
    Search by state, SCIAN sector, activity, business name or geographic radius.
  - **Yelp Fusion API:** businesses with reviews and ratings. Filter by category,
    price, rating, reviews, "open now", services and attributes.
  - **Google Places API:** global business directory from Google Maps. Multi-type
    text search, price range, minimum rating and "open now" filters.
- Wizard with source-specific filters and validation.
- Advanced filters: sector, type, size (employee stratum), location, rating, price.
- Automatic tagging by sector, category and place type.
- Deduplication by external ID (DENUE ID, Yelp ID, Place ID).
- Cross-source deduplication by business fingerprint (name + location / phone).
- Automatic assignment to sales team and salesperson.
- Website-based email enrichment with one click.
- CSV export of every mined lead.
- Persisted business data: rating, review count, price level, GPS coordinates.
- Connection testing per source from the settings screen.
- 100% Spanish interface.

## Requirements

External service credentials, configured in **Settings → CRM → Lead Mining**:

| Source | Credential | Where to get it |
|--------|------------|-----------------|
| DENUE (INEGI) | Free token | INEGI DENUE portal |
| Yelp Fusion | API key | Yelp developers |
| Google Places | API key | Google Cloud Console (Places API enabled) |

These services are only queried when you run a lead search; the data sent is
limited to your search terms and configured location.

## Installation

Copy the `crm_lead_fetcher` folder into your addons path, update the module list
and install **Lead Mining CRM (DENUE + Yelp + Google)** from the Apps menu.

## Usage

1. Open **CRM → Configuration → Minado de Leads**.
2. Choose a source, configure the filters and run the search.
3. Review and manage the generated leads from your CRM.

## Support

For issues with this module, contact the seller using the support email provided
with your purchase.

## License

LGPL-3
