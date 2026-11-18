
import requests

def test_get_pet_findByTags():

    url = "https://petstore.swagger.io/v2/pet/findByTags"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
