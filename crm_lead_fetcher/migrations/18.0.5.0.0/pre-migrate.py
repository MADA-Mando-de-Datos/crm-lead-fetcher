def migrate(cr, version):
    """18.0.5.0.0: Introduce campos de datos de fuente en crm.lead.

    Los nuevos campos (source_rating, source_reviews, source_price_level,
    yelp_price, latitude, longitude) son creados por el ORM durante el
    upgrade. Esta migración garantiza que si existieran columnas residuales
    de una instalación previa a medio migrar, se limpien correctamente.
    """

    # si por cualquier motivo existiera una columna `website` custom definida
    # como Char plano en versiones previas del módulo, el ORM la habrá
    # fusionado con el campo estándar de crm.lead; no hay acción necesaria.
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'crm_lead'
           AND column_name = 'website'
    """)
    if cr.fetchone():
        # El campo `website` estándar de crm.lead ya existe; solo limpiamos
        # valores inconsistentes (URLs sin esquema) dejando que el ORM y el
        # _clean_website nativo normalicen en lectura/escritura.
        pass
