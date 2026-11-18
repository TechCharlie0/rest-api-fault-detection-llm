
import requests

def test_get_user_logout():

    url = "https://petstore.swagger.io/v2/user/logout"

    response = requests.request(
        "GET",
        url
    )

    assert response.status_code < 500
