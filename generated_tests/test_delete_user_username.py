
import requests

def test_delete_user_username():

    url = "https://petstore.swagger.io/v2/user/testuser"

    response = requests.request(
        "DELETE",
        url
    )

    assert response.status_code < 500
