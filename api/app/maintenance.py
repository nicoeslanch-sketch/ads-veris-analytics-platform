"""Scheduled, bounded retention scans independent of customer navigation."""

import logging
import threading

from .commercial_rpc import commercial_rpc
from .routes.retention import _retention_sync

logger = logging.getLogger('uvicorn.error')


class RetentionScheduler:
    def __init__(self, settings):
        self.settings = settings
        self.stop = threading.Event()

    def poll(self):
        mode = self.settings.retention_schedule_mode
        if mode == 'off':
            return
        claim = commercial_rpc('retention_schedule_operation', {'p_action': 'claim'}, self.settings)
        if not claim:
            return
        report = dict(mode=mode, accounts=0, candidates=0, deleted=0, errors=0)
        for user_id in claim['users']:
            if self.stop.is_set():
                return
            report['accounts'] += 1
            try:
                result = _retention_sync(user_id, self.settings, dry_run=mode == 'audit')
                report['candidates'] += result['candidatos']
                report['deleted'] += result['eliminados']
                report['errors'] += int(bool(result.get('actividad_error')))
            except Exception:
                report['errors'] += 1
        commercial_rpc('retention_schedule_operation', {
            'p_action': 'complete', 'p_lease': claim['lease'], 'p_report': report}, self.settings)

    def run(self):
        while not self.stop.is_set():
            try:
                self.poll()
            except Exception:
                logger.warning('retention_schedule_unavailable')
            self.stop.wait(60)

    def shutdown(self):
        self.stop.set()
