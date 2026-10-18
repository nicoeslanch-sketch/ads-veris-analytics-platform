"""Signed, content-free webhook notifications with PostgreSQL retry leases."""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .commercial_rpc import commercial_rpc

logger = logging.getLogger('uvicorn.error')


def configured(settings):
    return bool(getattr(settings, 'operations_webhook_url', '') and getattr(settings, 'operations_webhook_secret', ''))


def deliver(settings, codes):
    if not configured(settings):
        return
    url = settings.operations_webhook_url
    destination = hashlib.sha256(url.encode()).hexdigest()
    commercial_rpc('operational_notification', {'p_action': 'sync', 'p_destination': destination,
                                               'p_codes': sorted(codes)}, settings)
    # A receiver deduplicates by event_id if a successful reply is lost.
    for _ in range(3):
        item = commercial_rpc('operational_notification', {'p_action': 'claim', 'p_destination': destination}, settings)
        if not item:
            return
        success = False
        try:
            host = urlsplit(url).hostname
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise ValueError('non_public_destination')
            event = {'event_id': hashlib.sha256(f"{destination}:{item['code']}:{item['revision']}".encode()).hexdigest(),
                     'service': 'ADS Veris', 'code': item['code'], 'state': 'active' if item['active'] else 'resolved',
                     'sent_at': datetime.now(timezone.utc).isoformat()}
            body = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
            signature = hmac.new(settings.operations_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            # No redirects, provider credentials, customer IDs, file names or content.
            with httpx.Client(timeout=httpx.Timeout(5), follow_redirects=False, trust_env=False) as client:
                with client.stream('POST', url, content=body, headers={
                    'Content-Type': 'application/json', 'X-ADS-Signature': 'sha256=' + signature}) as response:
                    success = 200 <= response.status_code < 300
        except Exception:
            logger.warning('operational_notification_delivery_failed')
        commercial_rpc('operational_notification', {'p_action': 'ack', 'p_destination': destination,
            'p_code': item['code'], 'p_lease': item['lease'], 'p_revision': item['revision'], 'p_success': success}, settings)
