"""Bounded, aggregate monitoring. It never inspects request or customer content."""

from collections import deque
import json
import logging
import threading
from time import monotonic
from uuid import uuid4

from .commercial_rpc import commercial_rpc

logger = logging.getLogger('uvicorn.error')


class RequestWindow:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.buckets = deque(maxlen=300)

    def record(self, status, elapsed_ms):
        now = int(self.clock())
        with self.lock:
            if not self.buckets or self.buckets[-1][0] != now:
                self.buckets.append([now, 0, 0, 0, 0])
            bucket = self.buckets[-1]
            bucket[1] += 1
            bucket[2] += status >= 500
            bucket[3] += status == 429
            bucket[4] += elapsed_ms >= 5000

    def snapshot(self):
        cutoff = int(self.clock()) - 300
        with self.lock:
            totals = [sum(row[index] for row in self.buckets if row[0] > cutoff) for index in range(1, 5)]
        return dict(zip(('requests', 'errors', 'limited', 'slow'), totals))


request_window = RequestWindow()


def alerts_for(snapshot):
    http, queue, storage = (snapshot.get(key, {}) for key in ('http', 'queue', 'storage'))
    alerts = []

    def add(code, title, detail, critical=False):
        alerts.append({'code': code, 'severity': 'critical' if critical else 'warning',
                       'title': title, 'detail': detail})

    if not http.get('instances'):
        add('MONITOR_STALE', 'Monitor sin senal reciente', 'No hay un latido de la API en los ultimos dos minutos. Revisa el servicio; no se puede afirmar que este sano.', True)
    total = http.get('requests', 0)
    if http.get('errors', 0) >= 5 and total and http['errors'] / total >= .05:
        add('HTTP_ERRORS', 'Errores del servidor', 'Al menos cinco errores y un 5% de respuestas 5xx en la ventana observada.', True)
    if http.get('limited', 0) >= 10 and total and http['limited'] / total >= .1:
        add('HTTP_LIMITED', 'Solicitudes limitadas', 'Un 10% o mas de solicitudes recibieron 429. Revisa abuso, cuotas y capacidad antes de ampliar recursos.')
    if http.get('slow', 0) >= 10 and total and http['slow'] / total >= .2:
        add('HTTP_SLOW', 'Respuestas lentas', 'Al menos diez solicitudes y un 20% tardaron cinco segundos o mas. Los trabajos asincronos se revisan por separado.')
    if queue.get('expired_leases', 0) or queue.get('long_running', 0):
        add('WORKER_STALLED', 'Procesamiento interrumpido o atascado', 'Revisa el worker: hay un arrendamiento vencido o un trabajo que supera veinte minutos.', True)
    if queue.get('oldest_wait_seconds', 0) >= 120:
        add('QUEUE_WAIT', 'Archivos esperando', 'El trabajo mas antiguo lleva al menos dos minutos en cola. Revisa la actividad del worker.')
    if queue.get('queued', 0) + queue.get('running', 0) >= queue.get('max_active', 32) * .8:
        add('QUEUE_PRESSURE', 'Cola cerca de su limite', 'Al menos un 80% de las plazas estan ocupadas. No aumentes concurrencia sin comprobar memoria y CPU.')
    if queue.get('failed_retained_15m', 0) >= 3:
        add('JOBS_FAILED', 'Varios procesos fallidos', 'Hay al menos tres fallos recientes en la cola conservada. Revisa los registros con su identificador de solicitud.')
    limit = storage.get('limit_bytes', 0)
    ratio = (storage.get('used_bytes', 0) + storage.get('reserved_bytes', 0)) / limit if limit else 0
    if ratio >= .8:
        add('STORAGE_PRESSURE', 'Almacenamiento cerca de su cuota', 'Uso y reservas superan el 80% del presupuesto. Revisa retencion y respaldos antes de eliminar archivos.', ratio >= .95)
    if storage.get('stale_reservations', 0):
        add('STORAGE_PENDING', 'Escrituras sin confirmar', 'Hay reservas de mas de treinta minutos. Confirma el resultado remoto antes de liberarlas; no se borran automaticamente.')
    if storage.get('unknown_sizes', 0):
        add('STORAGE_UNKNOWN', 'Tamano de archivos pendiente', 'Algunos objetos no declaran su tamano. La cuota reserva un margen conservador para ellos.')
    return alerts


def health_snapshot(settings):
    data = commercial_rpc('operational_health', {'p_action': 'snapshot'}, settings)
    return {**data, 'alerts': alerts_for(data), 'external_notifications_configured': False}


class OperationalMonitor:
    def __init__(self, settings):
        self.settings = settings
        self.stop = threading.Event()
        self.instance_id = str(uuid4())
        self.previous = set()

    def poll(self):
        try:
            data = commercial_rpc('operational_health', {'p_action': 'heartbeat',
                'p_instance_id': self.instance_id, 'p_sample': request_window.snapshot()}, self.settings)
            current = {item['code'] for item in alerts_for(data)}
        except Exception:
            # Only fixed codes leave this boundary; never provider responses.
            current = {'MONITOR_UNAVAILABLE'}
        for code in sorted(current - self.previous):
            logger.warning(json.dumps({'event': 'operational_alert', 'code': code, 'state': 'active'}))
        for code in sorted(self.previous - current):
            logger.info(json.dumps({'event': 'operational_alert', 'code': code, 'state': 'resolved'}))
        self.previous = current

    def run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(60)

    def shutdown(self):
        self.stop.set()
