"""
Descarga automática de establecimientos MINEDUC usando Selenium.
Simula exactamente la interacción de un navegador.
"""

import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
BASE_URL = "https://www.mineduc.gob.gt/BUSCAESTABLECIMIENTO_GE/"

DEPARTAMENTOS = [
    "ALTA VERAPAZ", "BAJA VERAPAZ", "CHIMALTENANGO", "CHIQUIMULA",
    "CIUDAD CAPITAL", "EL PROGRESO", "ESCUINTLA", "GUATEMALA",
    "HUEHUETENANGO", "IZABAL", "JALAPA", "JUTIAPA", "PETEN",
    "QUETZALTENANGO", "QUICHE", "RETALHULEU", "SACATEPEQUEZ",
    "SAN MARCOS", "SANTA ROSA", "SOLOLA", "SUCHITEPEQUEZ",
    "TOTONICAPAN", "ZACAPA",
]

NIVELES = ["TODOS", "DIVERSIFICADO"]   # "TODOS" para todos los niveles, "DIVERSIFICADO" para carreras
MODO_PRUEBA = True   # True: solo 2 departamentos; False: todos

# ============================================================================
# FUNCIÓN PRINCIPAL DE DESCARGA CON SELENIUM
# ============================================================================

def descargar_departamento_nivel_selenium(driver, departamento, nivel):
    """
    Usa Selenium para navegar:
      - Selecciona departamento y nivel.
      - Clic en "Buscar Establecimiento".
      - Clic en "Generar Archivo de Excel".
      - Descarga el archivo Excel (en realidad es HTML) y lo parsea.
    Devuelve DataFrame.
    """
    # Ir a la página principal
    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 10)

    # Seleccionar departamento
    select_depto = Select(wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_cmbDepartamento"))))
    select_depto.select_by_visible_text(departamento)
    time.sleep(1)  # esperar posible postback

    # Seleccionar nivel
    select_nivel = Select(wait.until(EC.presence_of_element_located((By.ID, "ContentPlaceHolder1_cmbNivel"))))
    select_nivel.select_by_visible_text(nivel)
    time.sleep(0.5)

    # Clic en "Buscar Establecimiento" (imagen)
    boton_buscar = wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_IbtnConsultar")))
    boton_buscar.click()
    time.sleep(3)  # esperar carga de resultados

    # Verificar que la tabla de resultados haya aparecido (o al menos que no haya error)
    try:
        # Buscar el botón "Generar Archivo de Excel"
        boton_excel = wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_IbtnExportarExcel")))
        boton_excel.click()
        time.sleep(3)  # esperar que se genere el archivo
    except TimeoutException:
        # Puede que no haya datos o haya error; intentar capturar mensaje
        try:
            error_msg = driver.find_element(By.XPATH, "//*[contains(text(),'No se encontraron')]").text
            print(f"  Sin datos para {departamento} - {nivel}: {error_msg}")
            return pd.DataFrame()  # DataFrame vacío
        except:
            print(f"  Error desconocido para {departamento} - {nivel}")
            raise

    # Obtener el HTML del Excel (está en una nueva ventana o en el mismo frame)
    # El sitio genera el Excel en la misma ventana, reemplazando el contenido.
    # Esperamos a que el cuerpo tenga una tabla.
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        html = driver.page_source
    except:
        # Si no hay tabla, puede ser que el Excel se descargue como archivo, pero en este caso es HTML.
        html = driver.page_source

    # Parsear el HTML para extraer la tabla
    tablas = pd.read_html(html)
    if not tablas:
        return pd.DataFrame()
    # La tabla principal suele ser la más grande
    df = max(tablas, key=lambda t: t.shape[0])
    # La primera fila suele ser el encabezado
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    df = df.dropna(how="all")
    # Agregar columnas de contexto
    df["DEPARTAMENTO_CONSULTADO"] = departamento
    df["NIVEL_CONSULTADO"] = nivel
    return df


# ============================================================================
# EJECUCIÓN PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    # Configurar Chrome headless (opcional)
    options = Options()
    options.add_argument("--headless")  # Comenta esta línea si quieres ver el navegador
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)  # Asegúrate de tener chromedriver en PATH

    try:
        # ---- Prueba con un departamento ----
        print("=== Prueba con ALTA VERAPAZ / TODOS ===")
        df_prueba = descargar_departamento_nivel_selenium(driver, "ALTA VERAPAZ", "TODOS")
        print(f"Filas obtenidas: {len(df_prueba)}")
        if not df_prueba.empty:
            print(df_prueba.head())

        # ---- Descarga completa ----
        departamentos_a_correr = DEPARTAMENTOS[:2] if MODO_PRUEBA else DEPARTAMENTOS
        resultados = []
        errores = []

        print(f"\nIniciando descarga para {len(departamentos_a_correr)} departamentos...")
        for depto in departamentos_a_correr:
            for nivel in NIVELES:
                try:
                    print(f"Procesando {depto} - {nivel}...")
                    df_temp = descargar_departamento_nivel_selenium(driver, depto, nivel)
                    if not df_temp.empty:
                        resultados.append(df_temp)
                        print(f"  OK -> {len(df_temp)} filas")
                    else:
                        print(f"  Sin datos")
                except Exception as e:
                    errores.append((depto, nivel, str(e)))
                    print(f"  ERROR: {e}")
                time.sleep(2)  # pausa entre consultas

        print(f"\nDescargas exitosas: {len(resultados)} | Errores: {len(errores)}")

        if not resultados:
            raise SystemExit("No se obtuvo ningún resultado.")

        # ---- Unificación y limpieza ----
        df_raw = pd.concat(resultados, ignore_index=True)
        df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
        print(f"\nTotal filas (antes de deduplicar): {len(df_raw)}")

        df = df_raw.copy()

        categoricas = ["DEPARTAMENTO", "MUNICIPIO", "NIVEL", "SECTOR", "AREA",
                       "STATUS", "MODALIDAD", "JORNADA", "PLAN", "DEPARTAMENTAL"]
        for col in categoricas:
            if col in df.columns:
                df[col] = df[col].astype(str).str.upper().str.strip()
                df[col] = df[col].replace({"NAN": pd.NA})

        if "TELEFONO" in df.columns:
            df["TELEFONO"] = df["TELEFONO"].astype(str).str.replace(r"\.0$", "", regex=True)
            df["TELEFONO"] = df["TELEFONO"].replace({"nan": pd.NA, "<NA>": pd.NA})

        if "CODIGO" in df.columns:
            antes = len(df)
            df["_no_nulos"] = df.notna().sum(axis=1)
            df = df.sort_values("_no_nulos", ascending=False).drop_duplicates(subset=["CODIGO"]).drop(columns="_no_nulos")
            print(f"Duplicados eliminados por CODIGO: {antes - len(df)}")

        print(f"Total filas final: {len(df)}")

        # ---- Exportar CSV ----
        SALIDA = "mineduc_establecimientos_unificado.csv"
        df.to_csv(SALIDA, index=False, encoding="utf-8-sig")
        print(f"\nArchivo guardado: {SALIDA} ({len(df)} filas, {len(df.columns)} columnas)")

    finally:
        driver.quit()