
import requests

def test_post_store_order():

    url = "https://petstore.swagger.io/v2/store/order"

    payload = {'id': 1, 'petId': 1, 'quantity': 1, 'shipDate': 'sample', 'status': 'placed', 'complete': True}

    response = requests.request(
        "POST",
        url,
        json=payload
    )

    assert response.status_code < 500
