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
    assert "ferspas-udf" in response.text


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


REPO = "https://github.com/yuiseki/poc-cng-ferspas-udf"


def test_the_index_is_titled_after_the_service(client):
    page = client.get("/").text
    assert "<title>ferspas-udf</title>" in page
    assert "ferspas-tile" not in page


def test_the_index_links_to_the_source(client):
    page = client.get("/").text
    assert page.count(REPO) >= 2  # the header button and the footer


def test_the_service_description_names_its_source(client):
    body = client.get("/service.json").json()
    assert body["service"] == "ferspas-udf"
    assert body["source"] == REPO


def test_no_viewer_page_still_says_ferspas_tile(client):
    for path in ("/", f"/viewer/analysis/{next(iter(REGISTRY))}"):
        assert "ferspas-tile" not in client.get(path).text, path


# -- caching ---------------------------------------------------------------
#
# Only tiles are worth holding at the edge. When the pages carried no
# Cache-Control, Cloudflare applied its own TTL and held them, so changing the
# viewer meant purging the zone and losing the tiles with it.


def test_pages_revalidate_so_a_deploy_does_not_need_a_purge(client):
    for path in ("/", f"/viewer/analysis/{next(iter(REGISTRY))}"):
        cache_control = client.get(path).headers["cache-control"]
        assert "no-cache" in cache_control, path


def test_metadata_revalidates_too(client):
    for path in ("/service.json", "/analysis"):
        assert "no-cache" in client.get(path).headers["cache-control"], path


def test_live_numbers_are_never_stored(client):
    for path in ("/cache", "/health"):
        assert client.get(path).headers["cache-control"] == "no-store", path


def test_a_page_carries_an_etag_so_revalidation_is_cheap(client):
    assert client.get("/").headers.get("etag")


def test_the_viewer_offers_buttons_for_a_phone(client):
    page = client.get(f"/viewer/analysis/{next(iter(REGISTRY))}").text
    assert 'id="prev"' in page
    assert 'id="next"' in page
    assert 'aria-label="previous month"' in page
    assert 'aria-label="next month"' in page


def test_the_viewer_reports_when_tiles_are_loading(client):
    page = client.get(f"/viewer/analysis/{next(iter(REGISTRY))}").text
    assert 'class="spinner"' in page
    assert "loading tiles" in page
    assert 'role="status"' in page  # announced, not only drawn


def test_the_viewer_guards_against_a_stale_load_finishing_last(client):
    # A load that finishes after you have moved on must not clear the
    # indicator for the month still loading.
    page = client.get(f"/viewer/analysis/{next(iter(REGISTRY))}").text
    assert "inFlight !== epoch" in page
    assert 'map.on("idle"' in page
