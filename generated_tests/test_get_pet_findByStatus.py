
import requests

def test_get_pet_findByStatus():

    url = "https://petstore.swagger.io/v2/pet/findByStatus"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
