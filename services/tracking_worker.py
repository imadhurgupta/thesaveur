"""
Celery Background Worker — Automated Courier Tracking
======================================================
Periodically polls active shipped orders for real courier scan updates.
Runs every 30 minutes (configurable via TRACKING_POLL_INTERVAL_MINUTES).

Start alongside gunicorn:
  celery -A services.tracking_worker.celery_app worker --loglevel=info -B
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
POLL_INTERVAL = int(os.environ.get('TRACKING_POLL_INTERVAL_MINUTES', '30'))

celery_app = Celery('tracking_worker', broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    beat_schedule={
        'poll-courier-tracking': {
            'task': 'services.tracking_worker.poll_all_active_orders',
            'schedule': crontab(minute=f'*/{POLL_INTERVAL}'),
        },
    },
)


@celery_app.task(name='services.tracking_worker.poll_all_active_orders',
                bind=True, max_retries=2, default_retry_delay=120)
def poll_all_active_orders(self):
    """
    Celery task: iterate all active shipped orders, fetch courier updates,
    auto-advance statuses. Skips orders polled within the last 25 minutes.
    """
    import datetime
    from services.tracking_service import (
        get_active_trackable_orders, update_order_from_tracking,
        get_system_setting
    )

    # Skip if auto-tracking is disabled by admin
    if get_system_setting('AUTO_TRACKING_ENABLED', '1') != '1':
        print('[WORKER] Auto-tracking disabled — skipping poll.')
        return {'skipped': True}

    orders = get_active_trackable_orders()
    print(f'[WORKER] Polling {len(orders)} active shipments...')

    updated, skipped, errors = 0, 0, 0
    threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=25)

    for order in orders:
        last_fetch = order.get('last_tracking_fetch')
        if last_fetch:
            try:
                lf_dt = datetime.datetime.fromisoformat(str(last_fetch).replace('Z', ''))
                if lf_dt > threshold:
                    skipped += 1
                    continue
            except Exception:
                pass
        try:
            result = update_order_from_tracking(order['id'])
            if result.get('changed'):
                updated += 1
        except Exception as e:
            errors += 1
            print(f'[WORKER] Error polling order #{order[id]}: {e}')

    summary = {'polled': len(orders), 'updated': updated,
               'skipped': skipped, 'errors': errors}
    print(f'[WORKER] Done: {summary}')
    return summary


@celery_app.task(name='services.tracking_worker.refresh_single_order')
def refresh_single_order(order_id: int, host_url: str = ''):
    """Celery task: immediately refresh tracking for one specific order."""
    from services.tracking_service import update_order_from_tracking
    return update_order_from_tracking(order_id, host_url=host_url)
