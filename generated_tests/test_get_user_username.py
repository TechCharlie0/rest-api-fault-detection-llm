
import requests

def test_get_user_username():

    url = "https://petstore.swagger.io/v2/user/testuser"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
