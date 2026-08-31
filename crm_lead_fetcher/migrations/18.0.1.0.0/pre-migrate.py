def migrate(cr, version):
    """Migra datos de crm_denue_leads a crm_lead_fetcher."""

    # 1. Renombrar campos en crm_lead
    if _column_exists(cr, 'crm_lead', 'denue_id'):
        cr.execute("ALTER TABLE crm_lead RENAME COLUMN denue_id TO external_id")
    if _column_exists(cr, 'crm_lead', 'denue_request_id'):
        cr.execute("ALTER TABLE crm_lead RENAME COLUMN denue_request_id TO lead_request_id")

    # 2. Renombrar modelo crm.denue.lead.request -> crm.lead.request
    cr.execute("""
        UPDATE ir_model
        SET model = 'crm.lead.request'
        WHERE model = 'crm.denue.lead.request'
    """)
    cr.execute("""
        UPDATE ir_model_fields
        SET model = 'crm.lead.request'
        WHERE model = 'crm.denue.lead.request'
    """)
    cr.execute("""
        UPDATE ir_model_data
        SET model = 'crm.lead.request'
        WHERE model = 'crm.denue.lead.request'
    """)

    # 3. Renombrar tabla principal
    if _table_exists(cr, 'crm_denue_lead_request'):
        cr.execute("ALTER TABLE crm_denue_lead_request RENAME TO crm_lead_request")

    # 4. Renombrar tablas M2M y columnas
    m2m_renames = [
        ('crm_denue_lead_request_crm_tag_rel', 'crm_lead_request_crm_tag_rel'),
        ('crm_denue_lead_request_crm_denue_sector_rel', 'crm_denue_sector_crm_lead_request_rel'),
        ('crm_denue_entidad_crm_denue_lead_request_rel', 'crm_denue_entidad_crm_lead_request_rel'),
    ]
    for old_t, new_t in m2m_renames:
        if _table_exists(cr, old_t):
            cr.execute(f"ALTER TABLE {old_t} RENAME TO {new_t}")
            if _column_exists(cr, new_t, 'crm_denue_lead_request_id'):
                cr.execute(f"ALTER TABLE {new_t} RENAME COLUMN crm_denue_lead_request_id TO crm_lead_request_id")

    # 5. Renombrar config parameters
    config_renames = [
        ('crm_denue_leads.token', 'crm_lead_fetcher.denue_token'),
        ('crm_denue_leads.entidad', 'crm_lead_fetcher.denue_entidad'),
        ('crm_denue_leads.max_records', 'crm_lead_fetcher.denue_max_records'),
        ('crm_denue_leads.sleep_seconds', 'crm_lead_fetcher.denue_sleep_seconds'),
    ]
    for old_key, new_key in config_renames:
        cr.execute("""
            UPDATE ir_config_parameter
            SET key = %s
            WHERE key = %s
        """, (new_key, old_key))

    # 6. Renombrar modulo en ir_model_data (entidades, sectores, etc.)
    cr.execute("""
        UPDATE ir_model_data
        SET module = 'crm_lead_fetcher'
        WHERE module = 'crm_denue_leads'
    """)


def _column_exists(cr, table, column):
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, (table, column))
    return cr.fetchone()[0]


def _table_exists(cr, table):
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table,))
    return cr.fetchone()[0]
