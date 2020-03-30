"""Test rdm handlers"""

from urllib.parse import urlparse

import pytest

from .utils import async_requests


@pytest.mark.parametrize(
    "old_url, new_url", [
        ("/rdm/test.somerdm.com/x1234", "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234/master"),
        ("/rdm/test.somerdm.com/x1234/", "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234/master"),
        ("/rdm/test.somerdm.com/x1234/osfstorage",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage/master"),
        ("/rdm/test.somerdm.com/x1234/osfstorage/test",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage%2Ftest/master"),
        ("/rdm/test.somerdm.com/x1234/osfstorage/test/",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage%2Ftest/master"),
        ("/rdm/test.somerdm.com/rcosrepo/import/x1234", "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234/master"),
        ("/rdm/test.somerdm.com/rcosrepo/import/x1234/", "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234/master"),
        ("/rdm/test.somerdm.com/rcosrepo/import/x1234/osfstorage",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage/master"),
        ("/rdm/test.somerdm.com/rcosrepo/import/x1234/osfstorage/test",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage%2Ftest/master"),
        ("/rdm/test.somerdm.com/rcosrepo/import/x1234/osfstorage/test/",
         "/v2/rdm/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ffiles%2Fosfstorage%2Ftest/master"),
    ]
)
async def test_rdm_redirect(app, old_url, new_url):
    r = await async_requests.get(app.url + old_url, allow_redirects=False)
    assert r.status_code == 302
    assert r.headers['location'] == new_url

@pytest.mark.parametrize(
    "old_url, new_url", [
        ("/weko3/test.somerdm.com/x1234/test.txt",
         "/v2/weko3/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ftest.txt/master"),
        ("/weko3/test.somerdm.com/x1234/test.txt,hoge.txt",
         "/v2/weko3/https%3A%2F%2Ftest.somerdm.com%2Fx1234%2Ftest.txt%2Choge.txt/master"),
    ]
)
async def test_weko3_redirect(app, old_url, new_url):
    r = await async_requests.get(app.url + old_url, allow_redirects=False)
    assert r.status_code == 302
    assert r.headers['location'] == new_url
