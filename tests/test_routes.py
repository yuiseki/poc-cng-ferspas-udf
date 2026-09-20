"""Routing: one page per function, and an index that lists them."""

import pytest
from fastapi.testclient import TestClient

from ferspas_tile.app import app
from ferspas_tile.functions import REGISTRY


@pytest.fixture(scope="module")
def client():
    # No `with`: entering the context manager would run the lifespan hook, which
    # builds every index over the network. These tests only touch routing.
    return TestClient(app, raise_server_exceptions=False)


def test_the_index_is_a_page_not_json(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ferspas-tile" in response.text


def test_the_service_description_moved_to_its_own_url(client):
    body = client.get("/service.json").json()
    assert body["endpoints"]["analysis_viewer"] == "/viewer/analysis/{id}"
    assert body["endpoints"]["index"] == "/"


def test_every_analysis_has_its_own_viewer_url(client):
    for analysis_id in REGISTRY:
        response = client.get(f"/viewer/analysis/{analysis_id}")
        assert response.status_code == 200, analysis_id
        assert response.headers["content-type"].startswith("text/html")


def test_an_unknown_analysis_is_404_before_a_page_is_served(client):
    # Better than a page that loads and then fails in the browser.
    response = client.get("/viewer/analysis/no-such-thing")
    assert response.status_code == 404
    assert "no-such-thing" in response.json()["detail"]


def test_the_old_viewer_url_redirects_to_the_index(client):
    response = client.get("/viewer", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == "/"


def test_the_viewer_page_has_no_picker_and_a_way_back(client):
    page = client.get(f"/viewer/analysis/{next(iter(REGISTRY))}").text
    assert "Return to index" in page
    assert "<select" not in page
