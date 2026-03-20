"""Integration tests for webhook stubs."""


class TestWebhooks:
    def test_hubspot_accepts_payload(self, api_client):
        resp = api_client.post(
            "/webhooks/hubspot",
            json=[{"eventId": 1, "subscriptionType": "contact.creation"}],
        )
        assert resp.status_code == 200

    def test_salesforce_accepts_payload(self, api_client):
        resp = api_client.post(
            "/webhooks/salesforce",
            json={"sobject": "Contact", "action": "updated"},
        )
        assert resp.status_code == 200
