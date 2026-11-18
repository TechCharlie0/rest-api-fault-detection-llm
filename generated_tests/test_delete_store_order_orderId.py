
import requests

def test_delete_store_order_orderId():

    url = "https://petstore.swagger.io/v2/store/order/1"

    response = requests.request(
        "DELETE",
        url
    )

    assert response.status_code < 500
