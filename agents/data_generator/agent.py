from services.schema_payload_generator import SchemaPayloadGenerator


class DataGeneratorAgent:

    def generate_payload(
        self,
        endpoint,
        method,
        state
    ):

        generator = SchemaPayloadGenerator()

        # Pet endpoints
        if (
            endpoint == "/pet"
            or endpoint.startswith("/pet/")
        ):

            payload = generator.generate(
                state.schemas.get("Pet"),
                state.schemas
            )

            payload["id"] = 1
            payload["name"] = "doggie"
            payload["status"] = "available"

            return payload

        # Order endpoints
        if "/store/order" in endpoint:

            payload = generator.generate(
                state.schemas.get("Order"),
                state.schemas
            )

            payload["id"] = 1
            payload["petId"] = 1
            payload["quantity"] = 1
            payload["shipDate"] = (
                "2025-01-01T00:00:00.000Z"
            )
            payload["status"] = "placed"
            payload["complete"] = True

            return payload

        # User endpoints
        if "/user" in endpoint:

            payload = generator.generate(
                state.schemas.get("User"),
                state.schemas
            )

            payload["id"] = 1
            payload["username"] = "testuser"
            payload["firstName"] = "John"
            payload["lastName"] = "Doe"
            payload["email"] = "john@test.com"
            payload["password"] = "123456"
            payload["phone"] = "123456789"
            payload["userStatus"] = 1

            if (
                "createWithArray" in endpoint
                or
                "createWithList" in endpoint
            ):
                return [payload]

            return payload

        return {}