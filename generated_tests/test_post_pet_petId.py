
import requests

def test_post_pet_petId():

    url = "https://petstore.swagger.io/v2/pet/1"

    payload = {'id': 1, 'category': 'sample', 'name': 'sample', 'photoUrls': ['sample'], 'tags': ['sample'], 'status': 'available'}

    response = requests.request(
        "POST",
        url,
        json=payload
    )

    assert response.status_code < 500
