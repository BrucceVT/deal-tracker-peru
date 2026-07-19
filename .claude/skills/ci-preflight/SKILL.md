---
name: ci-preflight
description: Checklist previo a desplegar o modificar el workflow de GitHub Actions del deal tracker — verifica modo --once, secretos, persistencia de DB y presupuesto de minutos.
---

# Preflight de CI (GitHub Actions)

Ejecutar este checklist antes de crear o modificar `.github/workflows/scan.yml`.
Contexto completo en `docs/PLAN.md` → Fase 5.

## Checklist

1. **Modo --once existe y funciona**: `python main.py --once` termina solo (sin el flag, el loop infinito colgaría el job hasta el timeout de 6h y quemaría minutos).
2. **Sin credenciales en el repo**: grep de `config.yaml` por tokens/webhooks reales. Los notifiers deben leer env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`) con prioridad sobre config.yaml.
3. **DB persistente**: el workflow hace checkout de la rama `data`, y al final commit+push de `data/deals.db` a esa rama (nunca a main).
4. **Cron desfasado**: minutos tipo `7,22,37,52`, nunca `0` ni `30` (retrasos de 5-30 min en horas pico; el schedule es best-effort).
5. **Presupuesto de minutos** (plan free privado = 2000 min/mes): estimar `duración_run × runs/día × 30`. Si excede: quitar Playwright del run (solo tiendas VTEX API), espaciar el cron, o hacer el repo público.
6. **Playwright solo si es imprescindible**: `playwright install chromium` añade ~2 min por run. Si todas las tiendas activas en CI usan API JSON, no instalarlo.
7. **`workflow_dispatch` habilitado** para poder probar runs manuales.
8. **Riesgo IP datacenter**: tras el primer run manual, revisar logs — si Falabella/Ripley devuelven 403/challenge, deshabilitarlas en la config de CI y anotar el hallazgo en docs/PLAN.md.
