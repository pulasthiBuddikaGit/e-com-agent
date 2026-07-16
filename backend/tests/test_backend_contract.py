import unittest

from pydantic import ValidationError

from backend.app import checkout_missing_fields, delivery_unavailable, extract_checkout_url
from backend.models import CheckoutCreateRequest
from backend.session_store import SessionStore


class BackendContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_cart_add_update_remove(self) -> None:
        store = SessionStore()
        session = await store.get_or_create()

        updated = await store.update_cart(
            session.session_id,
            "add",
            product_id="TEST123",
            quantity=2,
            product={"name": "Test Product", "price": "1,250", "currency": "LKR"},
        )
        self.assertEqual(len(updated.cart.items), 1)
        self.assertEqual(updated.cart.estimated_total, 2500.0)

        updated = await store.update_cart(
            session.session_id,
            "update",
            product_id="TEST123",
            quantity=1,
        )
        self.assertEqual(updated.cart.items[0].quantity, 1)

        updated = await store.update_cart(session.session_id, "remove", product_id="TEST123")
        self.assertEqual(updated.cart.items, [])

    def test_checkout_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(ValidationError):
            CheckoutCreateRequest.model_validate(
                {
                    "session_id": "abc",
                    "confirm": False,
                    "recipient": {"name": "Recipient", "phone": "0711111111"},
                    "delivery": {"city": "Colombo", "delivery_date": "2026-07-20"},
                    "sender": {"name": "Sender", "phone": "0722222222"},
                }
            )

    def test_checkout_missing_fields_are_specific(self) -> None:
        missing = checkout_missing_fields(
            cart_empty=True,
            recipient={"name": "Recipient"},
            delivery={"city": "Colombo"},
            sender={},
        )
        self.assertIn("cart", missing)
        self.assertIn("recipient.phone", missing)
        self.assertIn("delivery.delivery_date", missing)
        self.assertIn("delivery.address", missing)
        self.assertIn("sender.name", missing)

    def test_extract_checkout_url_from_nested_payload(self) -> None:
        payload = {"order": {"payment": {"pay_url": "https://pay.example/order/123"}}}
        self.assertEqual(extract_checkout_url(payload), "https://pay.example/order/123")

    def test_delivery_unavailable_detection(self) -> None:
        self.assertTrue(delivery_unavailable({"can_deliver": False}))
        self.assertTrue(delivery_unavailable({"delivery_status": "not deliverable"}))
        self.assertFalse(delivery_unavailable({"can_deliver": True}))


if __name__ == "__main__":
    unittest.main()
