
import requests

def test_delete_pet_petId():

    url = "https://petstore.swagger.io/v2/pet/1"

    response = requests.request(
        "DELETE",
        url
    )

    assert response.status_code < 500
