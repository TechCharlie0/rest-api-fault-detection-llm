class PayloadGenerator:

    def generate(self, endpoint):

        if endpoint.startswith("/pet"):
            return {
                "id": 1,
                "name": "doggie",
                "status": "available"
            }

        if endpoint.startswith("/user"):
            return {
                "id": 1,
                "username": "testuser",
                "firstName": "John",
                "lastName": "Doe",
                "email": "john@test.com",
                "password": "123456",
                "phone": "123456789"
            }

        if endpoint.startswith("/store/order"):
            return {
                "id": 1,
                "petId": 1,
                "quantity": 1,
                "shipDate": "2025-01-01T00:00:00.000Z",
                "status": "placed",
                "complete": True
            }

        return {}