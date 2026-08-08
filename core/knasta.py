"""
Integración con Knasta.pe para obtener historial de precios externo.
"""
import logging
import re
import json
from datetime import datetime
from urllib.parse import urlparse
import httpx

log = logging.getLogger("deal-tracker")

# Mapeo de nuestros nombres de tiendas a los de Knasta.pe
STORE_MAP = {
    "falabella": "falabella",
    "ripley": "ripley",
    "plazavea": "plazavea",
    "oechsle": "oechsle",
    "coolbox": "coolbox",
    "promart": "promart",
    "metro": "metro",
    "wong": "wong"
}

def clean_url(url: str) -> str:
    """Limpia la URL para comparación, quitando query params, fragmentos y
    el protocolo, estandarizando formato."""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".lower().rstrip("/")

async def get_knasta_history(title: str, store_url: str, store_name: str) -> list[tuple[float, float]] | None:
    """
    Busca un producto en Knasta.pe usando su título, empareja por URL/ID
    y descarga su historial de precios diario.
    
    Retorna una lista de (price, timestamp) ordenada de más reciente a más antiguo,
    o None si falla o no se encuentra.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    knasta_retail = STORE_MAP.get(store_name.lower())
    if not knasta_retail:
        log.warning("Knasta: Tienda '%s' no mapeada en STORE_MAP", store_name)
        return None
        
    async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
        # 1. Buscar en la API interna de búsqueda de Knasta
        search_url = "https://knasta.pe/api/results"
        try:
            resp = await client.get(search_url, params={"q": title})
            if resp.status_code != 200:
                log.warning("Knasta: Búsqueda falló con status %d", resp.status_code)
                return None
            search_data = resp.json()
        except Exception as e:
            log.warning("Knasta: Error llamando a la API de búsqueda: %s", e)
            return None
            
        products = search_data.get("products", [])
        if not products:
            log.info("Knasta: No se encontraron productos para '%s'", title)
            return None
            
        target_clean = clean_url(store_url)
        matched_product = None
        
        # 2. Emparejar producto exacto por URL
        for p in products:
            p_retail = p.get("retail")
            p_url = p.get("url")
            if not p_retail or not p_url:
                continue
                
            if p_retail.lower() == knasta_retail:
                if clean_url(p_url) == target_clean:
                    matched_product = p
                    break
        
        # Fallback: Emparejamiento difuso por ID/SKU en la URL
        if not matched_product:
            for p in products:
                p_retail = p.get("retail")
                p_url = p.get("url")
                if p_retail and p_retail.lower() == knasta_retail:
                    p_id = p.get("product_id")
                    if p_id and p_id in store_url:
                        matched_product = p
                        log.info("Knasta: Emparejamiento difuso por ID '%s' en la URL", p_id)
                        break
                        
        if not matched_product:
            log.info("Knasta: Producto '%s' no encontrado en el catálogo de Knasta para '%s'", title, store_name)
            return None
            
        # 3. Cargar página de detalles del producto matched
        p_id = matched_product.get("product_id")
        retail = matched_product.get("retail")
        
        detail_url = f"https://knasta.pe/detail/{retail}/{p_id}"
        try:
            resp = await client.get(detail_url)
            if resp.status_code != 200:
                log.warning("Knasta: Falló al cargar detalle con status %d", resp.status_code)
                return None
        except Exception as e:
            log.warning("Knasta: Error cargando detalle: %s", e)
            return None
            
        # 4. Extraer el __NEXT_DATA__ JSON del HTML
        next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
        if not next_data_match:
            log.warning("Knasta: No se encontró script __NEXT_DATA__ en la página de detalle")
            return None
            
        try:
            data = json.loads(next_data_match.group(1))
            product_info = data["props"]["pageProps"]["initialData"]["product"]
            dprices = product_info.get("dprices", [])
        except Exception as e:
            log.warning("Knasta: Error parseando __NEXT_DATA__ JSON: %s", e)
            return None
            
        # 5. Convertir la serie de tiempo a list[tuple[float, float]]
        history = []
        for item in dprices:
            price_val = item.get("price")
            date_str = item.get("date")
            if price_val is not None and date_str:
                try:
                    dt = datetime.strptime(date_str, "%d-%m-%Y")
                    history.append((float(price_val), dt.timestamp()))
                except ValueError:
                    continue
                    
        # Ordenar por timestamp descendente
        history.sort(key=lambda x: x[1], reverse=True)
        log.info("Knasta: Se recuperó exitosamente historial de %d días para '%s'", len(history), title)
        return history
