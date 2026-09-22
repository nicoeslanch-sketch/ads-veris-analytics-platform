"""A preparation checklist, not a payment activation or compliance certificate."""

from .account_security import mfa_enforced, security_context
from .config import Settings
from .durable_analysis import durable_mode
from .version import LATEST_MIGRATION


def commercial_readiness(user_id: str, settings: Settings) -> dict:
    context = security_context(user_id, settings)
    return {
        'payment_activation_available': False,
        'purchases_enabled': False,
        'database_migration_required': LATEST_MIGRATION,
        'items': [
            {'id': 'mfa', 'title': 'Doble factor de esta cuenta',
             'state': 'ready' if mfa_enforced(settings) and context['has_mfa'] else 'pending',
             'detail': 'Verificado contra la cuenta; administracion exige segundo factor en produccion.'},
            {'id': 'queue', 'title': 'Procesamiento persistente',
             'state': 'configured' if durable_mode(settings) in ('embedded', 'external') else 'pending',
             'detail': f"Modo configurado: {durable_mode(settings)}. No certifica capacidad ni disponibilidad del worker."},
            {'id': 'coins', 'title': 'ADS Coins', 'state': 'prepared',
             'detail': f"Creditos de servicio, sin valor de retiro. Costo configurado por mensaje avanzado: {settings.ads_coins_advanced_message_cost} Coins. No es un precio en pesos."},
            {'id': 'payments', 'title': 'Cobros con tarjeta', 'state': 'deferred',
             'detail': 'Pospuestos por el titular. Sin pasarela, tarjeta almacenada ni cargos. Requiere integracion y pruebas antes de activar.'},
            {'id': 'catalog', 'title': 'Precios y condiciones', 'state': 'pending',
             'detail': 'Falta aprobar precios en CLP, impuestos, renovacion, cancelacion y devoluciones.'},
            {'id': 'recovery', 'title': 'Recuperacion ante desastre', 'state': 'pending',
             'detail': 'Falta demostrar restauracion de base de datos y archivos desde una copia externa. Los snapshots analiticos no la sustituyen.'},
            {'id': 'capacity', 'title': 'Capacidad comercial', 'state': 'pending',
             'detail': 'Faltan pruebas sostenidas en la infraestructura objetivo y alertas operativas. No hay un numero certificado de usuarios simultaneos.'},
        ],
    }
