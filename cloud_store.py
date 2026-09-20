"""Persistent, server-only metadata for the synthetic public demo."""
import os
from uuid import UUID
import requests


class CloudStore:
    def __init__(self):
        self.url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1'
        key = os.environ['SUPABASE_SECRET_KEY']
        self.headers = {'apikey': key,
                        'Content-Type': 'application/json'}

    def call(self, method, path, **kwargs):
        response = requests.request(method, self.url + path, headers=self.headers,
                                    timeout=20, **kwargs)
        if not response.ok:
            # Never echo credential-bearing URLs or upstream response bodies.
            raise RuntimeError('METADATA_UNAVAILABLE')
        return response.json() if response.content else None

    def claim(self):
        rows = self.call('POST', '/rpc/claim_demo_run', json={})
        return rows[0] if rows else None

    def get(self, run_id):
        run_id = str(UUID(run_id))
        rows = self.call('GET', '/demo_runs', params={'id': 'eq.' + run_id,
                                                     'select': 'id,created_at,payload'})
        return rows[0] if rows else None

    def save(self, run_id, payload):
        self.call('PATCH', '/demo_runs', params={'id': 'eq.' + str(UUID(run_id))},
                  json={'payload': payload})
