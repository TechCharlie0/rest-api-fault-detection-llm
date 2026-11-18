
import requests

def test_get_pet_petId():

    url = "https://petstore.swagger.io/v2/pet/1"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
