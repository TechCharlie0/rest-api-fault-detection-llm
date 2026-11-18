
import requests

def test_get_store_inventory():

    url = "https://petstore.swagger.io/v2/store/inventory"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
