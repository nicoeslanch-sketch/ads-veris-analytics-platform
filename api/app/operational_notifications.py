"""Signed, content-free webhook notifications with PostgreSQL retry leases."""

import hashlib
import base64
import hmac
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx

from .commercial_rpc import commercial_rpc

logger = logging.getLogger('uvicorn.error')


def configured(settings):
    return email_configured(settings) or bool(getattr(settings, 'operations_webhook_url', '') and getattr(settings, 'operations_webhook_secret', ''))


def email_configured(settings):
    return all(getattr(settings, key, '') for key in ('operations_email_to', 'operations_email_from',
        'operations_gmail_client_id', 'operations_gmail_client_secret', 'operations_gmail_refresh_token'))


def _send_email(settings, event):
    # Gmail send-only OAuth authorization is configured by the mailbox owner.
    # This adapter never reads messages, asks for passwords, or follows redirects.
    with httpx.Client(timeout=httpx.Timeout(5), follow_redirects=False, trust_env=False) as client:
        response = client.post('https://oauth2.googleapis.com/token', data={
            'client_id': settings.operations_gmail_client_id,
            'client_secret': settings.operations_gmail_client_secret,
            'refresh_token': settings.operations_gmail_refresh_token,
            'grant_type': 'refresh_token',
        })
        if response.status_code != 200:
            return False
        token = response.json().get('access_token')
        if not isinstance(token, str) or not token:
            return False
        message = EmailMessage()
        message['From'] = settings.operations_email_from
        message['To'] = settings.operations_email_to
        state = 'Alerta' if event['state'] == 'active' else 'Recuperado'
        message['Subject'] = f"ADS Veris | {state}: {event['code']}"
        message['Message-ID'] = f"<{event['event_id']}@adsveris.com>"
        message.set_content(f"{state}: {event['code']}\nFecha UTC: {event['sent_at']}\n\n"
            "Revisa Estado operativo en la administracion de ADS Veris.\n"
            "Este aviso no contiene archivos ni informacion de clientes.\n"
            f"Referencia: {event['event_id']}\n")
        response = client.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
            headers={'Authorization': 'Bearer ' + token},
            json={'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('ascii')})
        return response.status_code == 200 and bool(response.json().get('id'))


def deliver(settings, codes):
    if not configured(settings):
        return
    email = email_configured(settings)
    url = settings.operations_webhook_url
    target = f'gmail:{settings.operations_email_from}:{settings.operations_email_to}' if email else url
    destination = hashlib.sha256(target.encode()).hexdigest()
    commercial_rpc('operational_notification', {'p_action': 'sync', 'p_destination': destination,
                                               'p_codes': sorted(codes)}, settings)
    # A receiver deduplicates by event_id if a successful reply is lost.
    for _ in range(3):
        item = commercial_rpc('operational_notification', {'p_action': 'claim', 'p_destination': destination}, settings)
        if not item:
            return
        success = False
        try:
            event = {'event_id': hashlib.sha256(f"{destination}:{item['code']}:{item['revision']}".encode()).hexdigest(),
                     'service': 'ADS Veris', 'code': item['code'], 'state': 'active' if item['active'] else 'resolved',
                     'sent_at': datetime.now(timezone.utc).isoformat()}
            if email:
                success = _send_email(settings, event)
            else:
                host = urlsplit(url).hostname
                addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                    raise ValueError('non_public_destination')
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
