import unittest

from hmr_order_collection.masking import mask_payload


class MaskPayloadTests(unittest.TestCase):
    def test_masks_sensitive_nested_fields_but_preserves_order_and_product_identifiers(self):
        payload = {
            "customer": {
                "name": "Ada Lovelace",
                "phone": "010-1234-5678",
                "tel": "02-123-4567",
                "address": "Seoul",
                "email": "ada@example.com",
                "customs_code": "P123456789",
                "token": "access-token",
                "secret": "top-secret",
                "api_key": "key-value",
            },
            "items": [{"product_id": "SKU-1", "product_name": "Cookie"}],
            "order_id": "ORDER-1",
        }

        self.assertEqual(
            mask_payload(payload),
            {
                "customer": {
                    "name": "***",
                    "phone": "***",
                    "tel": "***",
                    "address": "***",
                    "email": "***",
                    "customs_code": "***",
                    "token": "***",
                    "secret": "***",
                    "api_key": "***",
                },
                "items": [{"product_id": "SKU-1", "product_name": "Cookie"}],
                "order_id": "ORDER-1",
            },
        )


if __name__ == "__main__":
    unittest.main()
