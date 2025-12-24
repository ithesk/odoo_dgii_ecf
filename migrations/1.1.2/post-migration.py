# -*- coding: utf-8 -*-
"""
Migración automática para agregar el campo x_tipo_contribuyente a todos los partners existentes.
Este script se ejecuta automáticamente al actualizar el módulo.
"""

def migrate(cr, version):
    """
    Migración post-actualización para establecer valores por defecto en x_tipo_contribuyente.
    """
    print("\n" + "="*70)
    print("MIGRACIÓN: Agregando campo x_tipo_contribuyente")
    print("="*70)

    # Verificar si la columna existe
    cr.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'res_partner'
            AND column_name = 'x_tipo_contribuyente'
        )
    """)

    column_exists = cr.fetchone()[0]

    if not column_exists:
        print("⚠️  Columna x_tipo_contribuyente no existe, creándola...")
        cr.execute("""
            ALTER TABLE res_partner
            ADD COLUMN x_tipo_contribuyente VARCHAR
        """)
        print("✓ Columna creada")
    else:
        print("✓ Columna x_tipo_contribuyente ya existe")

    # Actualizar todos los partners a "consumo_final" por defecto
    print("\nActualizando partners existentes...")

    cr.execute("""
        UPDATE res_partner
        SET x_tipo_contribuyente = 'consumo_final'
        WHERE x_tipo_contribuyente IS NULL
    """)

    count = cr.rowcount
    print(f"✓ {count} partners actualizados a 'Consumidor Final'")

    # Actualizar partners con RNC validado a "credito_fiscal"
    cr.execute("""
        UPDATE res_partner
        SET x_tipo_contribuyente = 'credito_fiscal'
        WHERE x_rnc_validado = TRUE
        AND (x_tipo_contribuyente IS NULL OR x_tipo_contribuyente = 'consumo_final')
    """)

    count_credito = cr.rowcount
    print(f"✓ {count_credito} partners con RNC validado actualizados a 'Crédito Fiscal'")

    # Actualizar partners gubernamentales
    cr.execute("""
        UPDATE res_partner
        SET x_tipo_contribuyente = 'gubernamental'
        WHERE x_rnc_validado = TRUE
        AND (
            UPPER(name) LIKE '%AYUNTAMIENTO%' OR
            UPPER(name) LIKE '%MINISTERIO%' OR
            UPPER(name) LIKE '%GOBIERNO%' OR
            UPPER(name) LIKE '%MUNICIPAL%'
        )
    """)

    count_gub = cr.rowcount
    print(f"✓ {count_gub} partners gubernamentales actualizados")

    # Verificar/Corregir tipo 32
    print("\n" + "="*70)
    print("VERIFICACIÓN: Tipo 32 (Factura de Consumo)")
    print("="*70)

    cr.execute("""
        SELECT codigo, name, requiere_rnc
        FROM dgii_ecf_tipo
        WHERE codigo = '32'
    """)

    tipo32 = cr.fetchone()

    if tipo32:
        codigo, nombre, requiere_rnc = tipo32
        print(f"Tipo: {codigo} - {nombre}")
        print(f"Requiere RNC: {requiere_rnc}")

        if requiere_rnc:
            print("\n⚠️  CORRIGIENDO: Tipo 32 tiene requiere_rnc=True")
            cr.execute("""
                UPDATE dgii_ecf_tipo
                SET requiere_rnc = FALSE
                WHERE codigo = '32'
            """)
            print("✓ Tipo 32 corregido: requiere_rnc=False")
        else:
            print("✓ Tipo 32 configurado correctamente")
    else:
        print("❌ Tipo 32 NO encontrado")
        print("   NOTA: Se creará automáticamente al cargar el módulo")

    print("\n" + "="*70)
    print("✓ MIGRACIÓN COMPLETADA")
    print("="*70)

    # Mostrar resumen
    cr.execute("""
        SELECT
            x_tipo_contribuyente,
            COUNT(*) as total
        FROM res_partner
        WHERE x_tipo_contribuyente IS NOT NULL
        GROUP BY x_tipo_contribuyente
        ORDER BY total DESC
    """)

    print("\nRESUMEN:")
    for row in cr.fetchall():
        tipo, total = row
        print(f"  {tipo}: {total}")

    print("")
